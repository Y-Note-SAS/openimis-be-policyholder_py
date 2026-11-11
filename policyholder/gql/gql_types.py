import graphene
from contribution_plan.gql import ContributionPlanBundleGQLType
from core import prefix_filterset, ExtendedConnection
from core.gql_queries import UserGQLType
from graphene_django import DjangoObjectType
from core.gql.scoped_object_type import ScopedQuerysetMixin
from insuree.schema import InsureeGQLType
from location.gql_queries import LocationGQLType

from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderUser, PolicyHolderContributionPlan


class PolicyHolderGQLType(ScopedQuerysetMixin, DjangoObjectType):

    class Meta:
        model = PolicyHolder
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "version": ["exact"],
            "trade_name": ["exact", "istartswith", "icontains", "iexact"],
            **prefix_filterset("locations__", LocationGQLType._meta.filter_fields),
            "phone": ["exact", "istartswith", "icontains", "iexact"],
            "fax": ["exact", "istartswith", "icontains", "iexact"],
            "email": ["exact", "istartswith", "icontains", "iexact"],
            "legal_form": ["exact"],
            "activity_code": ["exact"],
            "accountancy_account": ["exact"],
            "payment_reference": ["exact"],
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"]
        }

        connection_class = ExtendedConnection


class PolicyHolderInsureeGQLType(ScopedQuerysetMixin, DjangoObjectType):

    class Meta:
        model = PolicyHolderInsuree
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "version": ["exact"],
            **prefix_filterset("policy_holder__", PolicyHolderGQLType._meta.filter_fields),
            **prefix_filterset("insuree__", InsureeGQLType._meta.filter_fields),
            **prefix_filterset("contribution_plan_bundle__", ContributionPlanBundleGQLType._meta.filter_fields),
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "user_created": ["exact"],
            "user_updated": ["exact"],
            "is_deleted": ["exact"]
        }

        connection_class = ExtendedConnection


class PolicyHolderContributionPlanGQLType(ScopedQuerysetMixin, DjangoObjectType):

    class Meta:
        model = PolicyHolderContributionPlan
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "version": ["exact"],
            **prefix_filterset("policy_holder__", PolicyHolderGQLType._meta.filter_fields),
            **prefix_filterset("contribution_plan_bundle__", ContributionPlanBundleGQLType._meta.filter_fields),
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "user_created": ["exact"],
            "user_updated": ["exact"],
            "is_deleted": ["exact"],
        }

        connection_class = ExtendedConnection


class PolicyHolderUserGQLType(ScopedQuerysetMixin, DjangoObjectType):

    class Meta:
        model = PolicyHolderUser
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "user": ["exact"],
            **prefix_filterset("policy_holder__", PolicyHolderGQLType._meta.filter_fields),
            **prefix_filterset("user__", UserGQLType._meta.filter_fields),
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "user_created": ["exact"],
            "user_updated": ["exact"],
            "is_deleted": ["exact"],
        }

        connection_class = ExtendedConnection
