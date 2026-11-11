
from contribution_plan.models import ContributionPlanBundle
from django.conf import settings
from django.db import models
from django.db.models import Q
from core import models as core_models
from location.models import Location
from insuree.models import Insuree
from policy.models import Policy


class PolicyHolderManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderManager, self).filter(*args, **kwargs)


class PolicyHolder(core_models.HistoryBusinessModel):
    code = models.CharField(db_column='PolicyHolderCode', max_length=32)
    trade_name = models.CharField(db_column='TradeName', max_length=255)
    locations = models.ForeignKey(Location, db_column='LocationsId', on_delete=models.deletion.DO_NOTHING, blank=True, null=True)
    address = models.JSONField(db_column='Address', blank=True, null=True)
    phone = models.CharField(db_column='Phone', max_length=16, blank=True, null=True)
    fax = models.CharField(db_column='Fax', max_length=16, blank=True, null=True)
    email = models.CharField(db_column='Email', max_length=255, blank=True, null=True)
    contact_name = models.JSONField(db_column='ContactName', blank=True, null=True)
    legal_form = models.IntegerField(db_column='LegalForm', blank=True, null=True)
    activity_code = models.IntegerField(db_column='ActivityCode', blank=True, null=True)
    accountancy_account = models.CharField(db_column='AccountancyAccount', max_length=64, blank=True, null=True)
    bank_account = models.JSONField(db_column="bankAccount", blank=True, null=True)
    payment_reference = models.CharField(db_column='PaymentReference', max_length=128, blank=True, null=True)

    objects = PolicyHolderManager()

    @classmethod
    def get_queryset(cls, queryset, user=None, *, validity=None, audits=None):
        """
        The policy holders `user` may see; validity / audits on request (OP-2029), every
        row otherwise (the resolvers state the legacy default through legacy_row_filters).

        - the policy holders `user` is linked to (a current PolicyHolderUser), always;
        - a portal-only user (a portal right, none of the module's global rights) sees
          nothing else: that link is the whole of their scope;
        - anyone else also sees the policy holders located in their districts (under
          ROW_SECURITY; a policy holder without location is not located, so not refused).
        The children (insurees, users, contribution plan bundles, contracts) inherit this
        through ParentScope("policy_holder").
        """
        queryset = cls.apply_row_filters(queryset, validity, audits, default=cls.filter_queryset)
        user = cls.scoping_user(user)
        if user is None or getattr(user, "is_anonymous", True):
            return cls.no_rows(queryset) if settings.ROW_SECURITY else queryset
        linked = Q(id__in=linked_policy_holder_ids(user))
        if is_portal_only_user(user):
            return queryset.filter(linked)
        if not settings.ROW_SECURITY or getattr(user, "is_imis_admin", False):
            return queryset
        from location.apps import LocationConfig
        if LocationConfig.no_location_check:
            return queryset
        location = cls.filter_location(user, paths=("locations",), loc_types=('R', 'D', 'W', 'V'))
        if not location:
            return queryset
        return queryset.filter(location[0] | linked)

    class Meta:
        db_table = 'tblPolicyHolder'


class PolicyHolderInsureeManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderInsureeManager, self).filter(*args, **kwargs)


class PolicyHolderInsuree(core_models.HistoryBusinessModel):
    # seen by whoever sees its policy holder (PolicyHolder.get_queryset)
    row_scope = core_models.ParentScope("policy_holder")

    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)
    insuree = models.ForeignKey(Insuree, db_column='InsureeId',
                                on_delete=models.deletion.DO_NOTHING)
    contribution_plan_bundle = models.ForeignKey(ContributionPlanBundle, db_column='ContributionPlanBundleId',
                                                 on_delete=models.deletion.DO_NOTHING, blank=True, null=True)
    last_policy = models.ForeignKey(Policy, db_column='LastPolicyId', on_delete=models.deletion.DO_NOTHING, blank=True, null=True)

    objects = PolicyHolderInsureeManager()

    class Meta:
        db_table = 'tblPolicyHolderInsuree'


class PolicyHolderContributionPlanManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderContributionPlanManager, self).filter(*args, **kwargs)


class PolicyHolderContributionPlan(core_models.HistoryBusinessModel):
    # seen by whoever sees its policy holder (PolicyHolder.get_queryset)
    row_scope = core_models.ParentScope("policy_holder")

    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)
    contribution_plan_bundle = models.ForeignKey(ContributionPlanBundle, db_column='ContributionPlanBundleId',
                                                 on_delete=models.deletion.DO_NOTHING)

    objects = PolicyHolderContributionPlanManager()

    class Meta:
        db_table = 'tblPolicyHolderContributionPlan'


class PolicyHolderUserManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderUserManager, self).filter(*args, **kwargs)


class PolicyHolderUser(core_models.HistoryBusinessModel):
    # seen by whoever sees its policy holder (PolicyHolder.get_queryset)
    row_scope = core_models.ParentScope("policy_holder")

    user = models.ForeignKey(
        core_models.User,
        db_column='UserID',
        on_delete=models.deletion.DO_NOTHING
    )
    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)

    objects = PolicyHolderUserManager()

    class Meta:
        db_table = 'tblPolicyHolderUser'


class PolicyHolderMutation(core_models.UUIDModel, core_models.ObjectMutation):
    policy_holder = models.ForeignKey(
        PolicyHolder,
        models.DO_NOTHING,
        related_name='mutations'
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder')

    class Meta:
        managed = True
        db_table = "policy_holder_PolicyHolderMutation"


class PolicyHolderInsureeMutation(core_models.UUIDModel):
    policy_holder_insuree = models.ForeignKey(
        PolicyHolderInsuree,
        models.DO_NOTHING,
        related_name='mutations'
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder_insuree')

    class Meta:
        managed = True
        db_table = "policy_holder_insuree_PolicyHolderInsureeMutation"


class PolicyHolderContributionPlanMutation(core_models.UUIDModel):
    policy_holder_contribution_plan = models.ForeignKey(
        PolicyHolderContributionPlan,
        models.DO_NOTHING,
        related_name='mutations'
    )
    mutation = models.ForeignKey(
        core_models.MutationLog,
        models.DO_NOTHING,
        related_name='policy_holder_contribution_plan'
    )

    class Meta:
        managed = True
        db_table = "policy_holder_contribution_plan_PolicyHolderContributionPlanMutation"


class PolicyHolderUserMutation(core_models.UUIDModel):
    policy_holder_user = models.ForeignKey(
        PolicyHolderUser, models.DO_NOTHING,
        related_name='mutations'
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder_user')

    class Meta:
        managed = True
        db_table = "policy_holder_user_PolicyHolderUserMutation"


def current_policy_holder_users(**kwargs):
    """The PolicyHolderUser links in force now (not deleted, within their validity)."""
    from core import datetime
    now = datetime.datetime.now()
    return PolicyHolderUser.objects.filter(
        Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=now),
        date_valid_from__lte=now,
        is_deleted=False,
        **kwargs,
    )


def linked_policy_holder_ids(user):
    """The ids of the policy holders `user` is linked to (the portal scope)."""
    user_id = getattr(user, "id", None)
    if user_id is None:
        return PolicyHolder.objects.none().values("id")
    return current_policy_holder_users(user_id=user_id).values("policy_holder_id")


def _holds_any(user, perm_lists):
    return any(perms and user.has_perms(perms) for perms in perm_lists)


def is_portal_only_user(user):
    """
    A policy holder portal user: holds a portal right of the module and none of its
    global (back-office) rights. Their scope is the policy holders they are linked to.
    """
    if getattr(user, "is_imis_admin", False):
        return False
    from policyholder.apps import PolicyholderConfig as cfg
    global_perms = [
        cfg.gql_query_policyholder_perms,
        cfg.gql_query_policyholderinsuree_perms,
        cfg.gql_query_policyholderuser_perms,
        cfg.gql_query_policyholdercontributionplanbundle_perms,
        cfg.gql_mutation_create_policyholder_perms,
        cfg.gql_mutation_update_policyholder_perms,
        cfg.gql_mutation_delete_policyholder_perms,
    ]
    if _holds_any(user, global_perms):
        return False
    portal_perms = [
        cfg.gql_query_policyholder_portal_perms,
        cfg.gql_query_policyholderinsuree_portal_perms,
        cfg.gql_query_policyholdercontributionplanbundle_portal_perms,
        cfg.gql_query_policyholderuser_portal_perms,
        cfg.gql_query_payment_portal_perms,
        cfg.gql_query_insuree_policy_portal_perms,
    ]
    return _holds_any(user, portal_perms)


def has_hybrid_phu_perms(user, ph, perms):
    """`perms` held by `user`, who is linked to the policy holder `ph` (portal rights)."""
    if ph is None:
        return False
    if user.has_perms(perms):
        # TODO make cache
        return current_policy_holder_users(policy_holder=ph, user_id=user.id).exists()
    return False
