"""
Security parity of the policy holder module: rows and writes stay within the policy
holders the user may see.

- PolicyHolder.get_queryset: the policy holders a user is linked to (PolicyHolderUser),
  plus, for anyone but a portal-only user, those located in their districts;
- PolicyHolderInsuree / PolicyHolderUser / PolicyHolderContributionPlan:
  ParentScope("policy_holder");
- the writes look their target, policy holder and insuree up within that scope, and a
  user cannot link themselves to a policy holder (that link grants its portal scope).

Fixture: core.test_helpers.create_security_tree -> R1>D1>W1>V1 / R2>D2>W2>V2; a policy
holder in each village with an insuree there; `user_a` holds the module's global rights
and is assigned district D1 only; `portal` holds the portal rights only and is linked to
the policy holder of V2.

Built without contribution_plan.tests.helpers (it imports a calculation rule Cameroon's
calcrule_contribution_income_percentage does not have).
"""
import datetime
import json

from django.core.cache import cache
from django.test import TestCase, override_settings

from contribution_plan.models import ContributionPlanBundle
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.test_helpers import (
    create_security_tree, create_right_only_user, create_test_interactive_user, get_test_token, perm_ids,
)
from insuree.test_helpers import create_test_insuree
from policyholder.apps import PolicyholderConfig as cfg
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderUser, \
    PolicyHolderContributionPlan


def _u(*lists):
    return list(dict.fromkeys(r for lst in lists for r in lst))


GLOBAL_RIGHTS = _u(*[perm_ids(getattr(cfg, name)) for name in (
    "gql_query_policyholder_perms", "gql_query_policyholderinsuree_perms", "gql_query_policyholderuser_perms",
    "gql_query_policyholdercontributionplanbundle_perms",
    "gql_mutation_create_policyholder_perms", "gql_mutation_update_policyholder_perms",
    "gql_mutation_create_policyholderinsuree_perms", "gql_mutation_update_policyholderinsuree_perms",
    "gql_mutation_replace_policyholderinsuree_perms",
    "gql_mutation_create_policyholderuser_perms", "gql_mutation_update_policyholderuser_perms",
    "gql_mutation_replace_policyholderuser_perms",
    "gql_mutation_create_policyholdercontributionplan_perms",
    "gql_mutation_update_policyholdercontributionplan_perms",
)])
PORTAL_RIGHTS = _u(*[perm_ids(getattr(cfg, name)) for name in (
    "gql_query_policyholder_portal_perms", "gql_query_policyholderinsuree_portal_perms",
    "gql_query_policyholderuser_portal_perms", "gql_query_policyholdercontributionplanbundle_portal_perms",
)])


def _build(cls, prefix):
    cls.t = create_security_tree(prefix)
    cls.saver = create_test_interactive_user(username=f"{prefix}saver")
    cls.bundle = ContributionPlanBundle(code=f"{prefix}CPB", name=f"{prefix} bundle")
    cls.bundle.save(user=cls.saver)
    for key, village in (("a", cls.t.v1), ("b", cls.t.v2)):
        ph = PolicyHolder(code=f"{prefix}PH{key}", trade_name=f"{prefix} trade {key}", locations=village,
                          date_valid_from=datetime.datetime(2020, 1, 1))
        ph.save(user=cls.saver)
        insuree = create_test_insuree(
            with_family=True, is_head=True,
            custom_props={"chf_id": f"{prefix}0000{1 if key == 'a' else 2}", "current_village": village},
            family_custom_props={"location": village})
        phi = PolicyHolderInsuree(policy_holder=ph, insuree=insuree, contribution_plan_bundle=cls.bundle,
                                  json_ext={}, date_valid_from=datetime.datetime(2020, 1, 1))
        phi.save(user=cls.saver)
        phcp = PolicyHolderContributionPlan(policy_holder=ph, contribution_plan_bundle=cls.bundle,
                                            date_valid_from=datetime.datetime(2020, 1, 1))
        phcp.save(user=cls.saver)
        setattr(cls, f"ph_{key}", ph)
        setattr(cls, f"ins_{key}", insuree)
        setattr(cls, f"phi_{key}", phi)
        setattr(cls, f"phcp_{key}", phcp)
    cls.user_a = create_right_only_user(f"{prefix.lower()}usera", GLOBAL_RIGHTS, [cls.t.d1.id])
    cls.portal = create_right_only_user(f"{prefix.lower()}portal", PORTAL_RIGHTS)
    cls.other = create_right_only_user(f"{prefix.lower()}other", [])
    cls.phu_b = PolicyHolderUser(user=cls.portal, policy_holder=cls.ph_b, date_valid_from=datetime.datetime(2020, 1, 1))
    cls.phu_b.save(user=cls.saver)


def _ids(queryset):
    return set(queryset.values_list("id", flat=True))


@override_settings(ROW_SECURITY=True)
class PolicyHolderReadScopeTest(openIMISGraphQLTestCase):

    @classmethod
    def setUpTestData(cls):
        _build(cls, "PHR")

    def setUp(self):
        cache.clear()

    def _q(self, query, user):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {get_test_token(user)}"}
        content = json.loads(self.query(query, headers=headers).content)
        self.assertNotIn("errors", content, content.get("errors"))
        return content["data"]

    def test_model_scope_by_district(self):
        ids = _ids(PolicyHolder.get_queryset(PolicyHolder.objects.all(), self.user_a))
        self.assertIn(self.ph_a.id, ids)
        self.assertNotIn(self.ph_b.id, ids)

    def test_portal_user_sees_the_linked_policy_holder_only(self):
        ids = _ids(PolicyHolder.get_queryset(PolicyHolder.objects.all(), self.portal))
        self.assertEqual({self.ph_b.id}, ids & {self.ph_a.id, self.ph_b.id})
        data = self._q('{ policyHolder { edges { node { code } } } }', self.portal)
        self.assertEqual({"PHRPHb"}, {e["node"]["code"] for e in data["policyHolder"]["edges"]})

    def test_portal_only_user_does_not_see_unlocated_policy_holders(self):
        floating = PolicyHolder(code="PHRfloat", trade_name="floating", date_valid_from=datetime.datetime(2020, 1, 1))
        floating.save(user=self.saver)
        self.assertNotIn(floating.id, _ids(PolicyHolder.get_queryset(PolicyHolder.objects.all(), self.portal)))
        self.assertIn(floating.id, _ids(PolicyHolder.get_queryset(PolicyHolder.objects.all(), self.user_a)))

    def test_policy_holder_query_needs_a_right(self):
        content = json.loads(self.query('{ policyHolder { edges { node { code } } } }', headers={
            "HTTP_AUTHORIZATION": f"Bearer {get_test_token(self.other)}"}).content)
        self.assertTrue(content.get("errors"), content)

    def test_children_follow_the_policy_holder(self):
        self.assertEqual({self.phi_a.id}, _ids(PolicyHolderInsuree.get_queryset(
            PolicyHolderInsuree.objects.filter(id__in=[self.phi_a.id, self.phi_b.id]), self.user_a)))
        self.assertEqual({self.phcp_a.id}, _ids(PolicyHolderContributionPlan.get_queryset(
            PolicyHolderContributionPlan.objects.filter(id__in=[self.phcp_a.id, self.phcp_b.id]), self.user_a)))
        self.assertNotIn(self.phu_b.id, _ids(PolicyHolderUser.get_queryset(PolicyHolderUser.objects.all(), self.user_a)))
        self.assertEqual({self.phi_b.id}, _ids(PolicyHolderInsuree.get_queryset(
            PolicyHolderInsuree.objects.filter(id__in=[self.phi_a.id, self.phi_b.id]), self.portal)))

    def test_policy_holder_insuree_listed_within_scope(self):
        data = self._q('{ policyHolderInsuree { edges { node { policyHolder { code } } } } }', self.user_a)
        codes = {e["node"]["policyHolder"]["code"] for e in data["policyHolderInsuree"]["edges"]}
        self.assertIn("PHRPHa", codes)
        self.assertNotIn("PHRPHb", codes)

    def test_policy_holder_contribution_plan_bundle_listed_within_scope(self):
        data = self._q('{ policyHolderContributionPlanBundle { edges { node { policyHolder { code } } } } }',
                       self.user_a)
        codes = {e["node"]["policyHolder"]["code"] for e in data["policyHolderContributionPlanBundle"]["edges"]}
        self.assertIn("PHRPHa", codes)
        self.assertNotIn("PHRPHb", codes)

    def test_default_validity_hides_deleted_rows(self):
        PolicyHolderInsuree.objects.filter(id=self.phi_a.id).update(is_deleted=True)
        data = self._q('{ policyHolderInsuree(applyDefaultValidityFilter: true) '
                       '{ edges { node { policyHolder { code } } } } }', self.user_a)
        self.assertNotIn("PHRPHa", {e["node"]["policyHolder"]["code"] for e in data["policyHolderInsuree"]["edges"]})
        everything = self._q('{ policyHolderInsuree { edges { node { policyHolder { code } } } } }', self.user_a)
        self.assertIn("PHRPHa", {e["node"]["policyHolder"]["code"]
                                 for e in everything["policyHolderInsuree"]["edges"]})


@override_settings(ROW_SECURITY=True)
class PolicyHolderWriteScopeTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        _build(cls, "PHW")

    def setUp(self):
        cache.clear()

    # --- PolicyHolderUser: the link granting the portal scope ---------------------
    def _link(self, user, target_user, policy_holder):
        from policyholder.gql.gql_mutations.create_mutations import CreatePolicyHolderUserMutation
        return CreatePolicyHolderUserMutation.async_mutate(user, **{
            "user_id": target_user.id, "policy_holder_id": policy_holder.id,
            "date_valid_from": datetime.date(2024, 1, 1)})

    def test_linking_oneself_refused(self):
        result = self._link(self.user_a, self.user_a, self.ph_a)
        self.assertTrue(result, "refused")
        self.assertFalse(PolicyHolderUser.objects.filter(user=self.user_a).exists())

    def test_linking_on_a_policy_holder_out_of_scope_refused(self):
        result = self._link(self.user_a, self.other, self.ph_b)
        self.assertTrue(result, "refused")
        self.assertFalse(PolicyHolderUser.objects.filter(user=self.other).exists())

    def test_linking_another_user_in_scope_allowed(self):
        self.assertIsNone(self._link(self.user_a, self.other, self.ph_a))
        self.assertTrue(PolicyHolderUser.objects.filter(user=self.other, policy_holder=self.ph_a).exists())

    def test_link_update_out_of_scope_refused(self):
        from policyholder.gql.gql_mutations.update_mutations import UpdatePolicyHolderUserMutation
        result = UpdatePolicyHolderUserMutation.async_mutate(self.user_a, **{
            "id": self.phu_b.id, "user_id": self.other.id})
        self.assertTrue(result, "refused")
        self.assertEqual(self.portal.id, PolicyHolderUser.objects.get(id=self.phu_b.id).user_id)

    def test_link_update_moving_oneself_in_refused(self):
        from policyholder.gql.gql_mutations.update_mutations import UpdatePolicyHolderUserMutation
        link = PolicyHolderUser(user=self.other, policy_holder=self.ph_a, date_valid_from=datetime.datetime(2020, 1, 1))
        link.save(user=self.saver)
        result = UpdatePolicyHolderUserMutation.async_mutate(self.user_a, **{"id": link.id, "user_id": self.user_a.id})
        self.assertTrue(result, "refused")
        self.assertEqual(self.other.id, PolicyHolderUser.objects.get(id=link.id).user_id)

    def test_link_replace_out_of_scope_refused(self):
        from policyholder.gql.gql_mutations.replace_mutation import ReplacePolicyHolderUserMutation
        result = ReplacePolicyHolderUserMutation.async_mutate(self.user_a, **{
            "uuid": self.phu_b.id, "user_id": self.other.id, "date_valid_from": datetime.date(2024, 1, 1)})
        self.assertTrue(result, "refused")
        self.assertIsNone(PolicyHolderUser.objects.get(id=self.phu_b.id).replacement_uuid)
        self.assertFalse(PolicyHolderUser.objects.filter(user=self.other).exists())

    # --- PolicyHolderInsuree / PolicyHolderContributionPlan ------------------------
    def _add_insuree(self, policy_holder, insuree):
        from policyholder.gql.gql_mutations.create_mutations import CreatePolicyHolderInsureeMutation
        return CreatePolicyHolderInsureeMutation.async_mutate(self.user_a, **{
            "policy_holder_id": policy_holder.id, "insuree_id": insuree.id,
            "contribution_plan_bundle_id": self.bundle.id, "date_valid_from": datetime.date(2024, 1, 1)})

    def test_insuree_added_to_a_policy_holder_out_of_scope_refused(self):
        self.assertTrue(self._add_insuree(self.ph_b, self.ins_a), "refused")
        self.assertFalse(PolicyHolderInsuree.objects.filter(policy_holder=self.ph_b, insuree=self.ins_a).exists())

    def test_insuree_out_of_scope_refused(self):
        self.assertTrue(self._add_insuree(self.ph_a, self.ins_b), "refused")
        self.assertFalse(PolicyHolderInsuree.objects.filter(policy_holder=self.ph_a, insuree=self.ins_b).exists())

    def test_insuree_in_scope_allowed(self):
        PolicyHolderInsuree.objects.filter(id=self.phi_a.id).update(is_deleted=True)
        self.assertIsNone(self._add_insuree(self.ph_a, self.ins_a))
        self.assertTrue(PolicyHolderInsuree.objects.filter(
            policy_holder=self.ph_a, insuree=self.ins_a, is_deleted=False).exists())

    def test_insuree_moved_to_a_policy_holder_out_of_scope_refused(self):
        from policyholder.gql.gql_mutations.update_mutations import UpdatePolicyHolderInsureeMutation
        result = UpdatePolicyHolderInsureeMutation.async_mutate(self.user_a, **{
            "id": self.phi_a.id, "policy_holder_id": self.ph_b.id})
        self.assertTrue(result, "refused")
        self.assertEqual(self.ph_a.id, PolicyHolderInsuree.objects.get(id=self.phi_a.id).policy_holder_id)

    def test_contribution_plan_on_a_policy_holder_out_of_scope_refused(self):
        from policyholder.gql.gql_mutations.create_mutations import CreatePolicyHolderContributionPlanMutation
        before = PolicyHolderContributionPlan.objects.filter(policy_holder=self.ph_b).count()
        result = CreatePolicyHolderContributionPlanMutation.async_mutate(self.user_a, **{
            "policy_holder_id": self.ph_b.id, "contribution_plan_bundle_id": self.bundle.id,
            "date_valid_from": datetime.date(2024, 1, 1)})
        self.assertTrue(result, "refused")
        self.assertEqual(before, PolicyHolderContributionPlan.objects.filter(policy_holder=self.ph_b).count())

    # --- PolicyHolder -----------------------------------------------------------
    def test_policy_holder_update_out_of_scope_refused(self):
        from policyholder.gql.gql_mutations.update_mutations import UpdatePolicyHolderMutation
        result = UpdatePolicyHolderMutation.async_mutate(self.user_a, **{"id": self.ph_b.id, "trade_name": "taken"})
        self.assertTrue(result, "refused")
        self.assertEqual("PHW trade b", PolicyHolder.objects.get(id=self.ph_b.id).trade_name)

    def test_policy_holder_moved_out_of_the_districts_refused(self):
        from policyholder.gql.gql_mutations.update_mutations import UpdatePolicyHolderMutation
        result = UpdatePolicyHolderMutation.async_mutate(self.user_a, **{
            "id": self.ph_a.id, "locations_id": self.t.v2.id})
        self.assertTrue(result, "refused")
        self.assertEqual(self.t.v1.id, PolicyHolder.objects.get(id=self.ph_a.id).locations_id)
