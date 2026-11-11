import graphene
import graphene_django_optimizer as gql_optimizer

from django.db.models import Q
from core.schema import OrderedDjangoFilterConnectionField, signal_mutation_module_validate
from core.services import wait_for_mutation
from core.gql import legacy_row_filters
from core.models import Validity
from location.services import get_ancestor_location_filter
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderUser, \
    PolicyHolderContributionPlan, PolicyHolderMutation, PolicyHolderInsureeMutation, \
    PolicyHolderContributionPlanMutation, PolicyHolderUserMutation
from policyholder.gql.gql_mutations.create_mutations import CreatePolicyHolderMutation, \
    CreatePolicyHolderInsureeMutation, CreatePolicyHolderUserMutation, CreatePolicyHolderContributionPlanMutation
from policyholder.gql.gql_mutations.delete_mutations import DeletePolicyHolderMutation, \
    DeletePolicyHolderInsureeMutation, DeletePolicyHolderUserMutation, DeletePolicyHolderContributionPlanMutation
from policyholder.gql.gql_mutations.update_mutations import UpdatePolicyHolderMutation, \
    UpdatePolicyHolderInsureeMutation, UpdatePolicyHolderUserMutation, UpdatePolicyHolderContributionPlanMutation
from policyholder.gql.gql_mutations.replace_mutation import ReplacePolicyHolderInsureeMutation, \
    ReplacePolicyHolderContributionPlanMutation, ReplacePolicyHolderUserMutation

from policyholder.apps import PolicyholderConfig
from policyholder.services import PolicyHolder as PolicyHolderServices
from policyholder.gql.gql_types import PolicyHolderUserGQLType, PolicyHolderGQLType, PolicyHolderInsureeGQLType, \
    PolicyHolderContributionPlanGQLType

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from payment.signals import signal_before_payment_query
from .signals import append_policy_holder_filter


class Query(graphene.ObjectType):
    policy_holder = OrderedDjangoFilterConnectionField(
        PolicyHolderGQLType,
        parent_location=graphene.String(),
        parent_location_level=graphene.Int(),
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean(),
        clientMutationId=graphene.String()
    )

    policy_holder_insuree = OrderedDjangoFilterConnectionField(
        PolicyHolderInsureeGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean()
    )

    policy_holder_user = OrderedDjangoFilterConnectionField(
        PolicyHolderUserGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean()
    )

    policy_holder_contribution_plan_bundle = OrderedDjangoFilterConnectionField(
        PolicyHolderContributionPlanGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean()
    )
    validate_policy_holder_code = graphene.Field(
        graphene.Boolean,
        policy_holder_code=graphene.String(required=True),
        description="Checks that the specified policy holder code is unique."
    )

    def resolve_validate_policy_holder_code(self, info, **kwargs):
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholder_perms):
            raise PermissionDenied(_("unauthorized"))
        errors = PolicyHolderServices.check_unique_code_policy_holder(code=kwargs['policy_holder_code'])
        return False if errors else True

    def resolve_policy_holder(self, info, **kwargs):
        # the global right, or the portal one; the rows are narrowed by
        # PolicyHolder.get_queryset (PolicyHolderGQLType): the districts for a global user,
        # the policy holders a portal user is linked to
        user = info.context.user
        if not (user.has_perms(PolicyholderConfig.gql_query_policyholder_perms)
                or user.has_perms(PolicyholderConfig.gql_query_policyholder_portal_perms)):
            raise PermissionDenied(_("unauthorized"))
        filters = []
        _legacy_validity(info, kwargs)

        client_mutation_id = kwargs.pop("clientMutationId", None)
        if client_mutation_id:
            wait_for_mutation(client_mutation_id)
            filters.append(Q(mutations__mutation__client_mutation_id=client_mutation_id))

        parent_location = kwargs.get('parent_location')
        if parent_location:
            filters += [get_ancestor_location_filter(parent_location, location_field='locations')]

        return gql_optimizer.query(PolicyHolder.objects.filter(*filters).all(), info)

    def resolve_policy_holder_insuree(self, info, **kwargs):
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderinsuree_perms):
            if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderinsuree_portal_perms):
                raise PermissionError("Unauthorized")
        # rows narrowed to the policy holders in scope by PolicyHolderInsuree.get_queryset
        _legacy_validity(info, kwargs)
        return gql_optimizer.query(PolicyHolderInsuree.objects.all(), info)

    def resolve_policy_holder_user(self, info, **kwargs):
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderuser_perms):
            if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderuser_portal_perms):
                raise PermissionError("Unauthorized")
        _legacy_validity(info, kwargs)
        return gql_optimizer.query(PolicyHolderUser.objects.all(), info)

    def resolve_policy_holder_contribution_plan_bundle(self, info, **kwargs):
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholdercontributionplanbundle_perms):
            if not info.context.user.has_perms(
                    PolicyholderConfig.gql_query_policyholdercontributionplanbundle_portal_perms):
                raise PermissionError("Unauthorized")
        _legacy_validity(info, kwargs)
        return gql_optimizer.query(PolicyHolderContributionPlan.objects.all(), info)


def _legacy_validity(info, kwargs):
    """
    The validity is applied by the models' get_queryset (OP-2029); the legacy arguments
    keep their meaning: dateValidFrom__Gte / dateValidTo__Lte a business validity range,
    applyDefaultValidityFilter the rows valid now, nothing at all every row.
    """
    if kwargs.get('dateValidFrom__Gte') or kwargs.get('dateValidTo__Lte'):
        return legacy_row_filters(info, kwargs)
    validity = Validity.NOW if kwargs.get('applyDefaultValidityFilter') else Validity.ALL
    return legacy_row_filters(info, kwargs, validity=validity)


class Mutation(graphene.ObjectType):
    create_policy_holder = CreatePolicyHolderMutation.Field()
    create_policy_holder_insuree = CreatePolicyHolderInsureeMutation.Field()
    create_policy_holder_user = CreatePolicyHolderUserMutation.Field()
    create_policy_holder_contribution_plan_bundle = CreatePolicyHolderContributionPlanMutation.Field()

    update_policy_holder = UpdatePolicyHolderMutation.Field()
    update_policy_holder_insuree = UpdatePolicyHolderInsureeMutation.Field()
    update_policy_holder_user = UpdatePolicyHolderUserMutation.Field()
    update_policy_holder_contribution_plan_bundle = UpdatePolicyHolderContributionPlanMutation.Field()

    delete_policy_holder = DeletePolicyHolderMutation.Field()
    delete_policy_holder_insuree = DeletePolicyHolderInsureeMutation.Field()
    delete_policy_holder_user = DeletePolicyHolderUserMutation.Field()
    delete_policy_holder_contribution_plan_bundle = DeletePolicyHolderContributionPlanMutation.Field()

    replace_policy_holder_insuree = ReplacePolicyHolderInsureeMutation.Field()
    replace_policy_holder_user = ReplacePolicyHolderUserMutation.Field()
    replace_policy_holder_contribution_plan_bundle = ReplacePolicyHolderContributionPlanMutation.Field()


def on_policy_holder_mutation(sender, **kwargs):
    uuid = kwargs['data'].get('uuid', None)
    if not uuid:
        return []
    if "PolicyHolderMutation" in str(sender._mutation_class):
        impacted_policy_holder = PolicyHolder.objects.get(id=uuid)
        PolicyHolderMutation.objects.create(
            policy_holder=impacted_policy_holder, mutation_id=kwargs['mutation_log_id'])
    if "PolicyHolderInsuree" in str(sender._mutation_class):
        impacted_policy_holder_insuree = PolicyHolderInsuree.objects.get(id=uuid)
        PolicyHolderInsureeMutation.objects.create(
            policy_holder_insuree=impacted_policy_holder_insuree, mutation_id=kwargs['mutation_log_id'])
    if "PolicyHolderContributionPlan" in str(sender._mutation_class):
        impacted_policy_holder_contribution_plan = PolicyHolderContributionPlan.objects.get(id=uuid)
        PolicyHolderContributionPlanMutation.objects.create(
            policy_holder_contribution_plan=impacted_policy_holder_contribution_plan,
            mutation_id=kwargs['mutation_log_id'])
    if "PolicyHolderUser" in str(sender._mutation_class):
        impacted_policy_holder_user = PolicyHolderUser.objects.get(id=uuid)
        PolicyHolderUserMutation.objects.create(
            policy_holder_user=impacted_policy_holder_user, mutation_id=kwargs['mutation_log_id'])
    return []


def bind_signals():
    signal_mutation_module_validate["policyholder"].connect(on_policy_holder_mutation)
    signal_before_payment_query.connect(append_policy_holder_filter)
