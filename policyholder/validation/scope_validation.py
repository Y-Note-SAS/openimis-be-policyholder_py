"""
Writes stay within what the author may see: the policy holder, insuree and user a
mutation names are looked up within the author's scope, never trusted as given.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from policyholder.models import PolicyHolder


class ScopeValidation:

    @classmethod
    def policy_holder(cls, user, policy_holder_id):
        """The current policy holder `policy_holder_id` if `user` may see it, else an error."""
        policy_holder = PolicyHolder.get_queryset(
            PolicyHolder.objects.filter(id=policy_holder_id, is_deleted=False), user
        ).first() if policy_holder_id else None
        if policy_holder is None:
            raise ValidationError(_("policyholder.validation.policy_holder_not_found") % {'id': policy_holder_id})
        return policy_holder

    @classmethod
    def insuree(cls, user, insuree_id):
        """The current insuree `insuree_id` if `user` may see it (Insuree.get_queryset)."""
        from insuree.models import Insuree
        insuree = Insuree.get_queryset(
            Insuree.objects.filter(id=insuree_id, validity_to__isnull=True), user
        ).first() if insuree_id else None
        if insuree is None:
            raise ValidationError(_("policyholder.validation.insuree_not_found") % {'id': insuree_id})
        return insuree

    @classmethod
    def contribution_plan_bundle(cls, contribution_plan_bundle_id):
        from contribution_plan.models import ContributionPlanBundle
        if not contribution_plan_bundle_id:
            return None
        bundle = ContributionPlanBundle.objects.filter(id=contribution_plan_bundle_id, is_deleted=False).first()
        if bundle is None:
            raise ValidationError(
                _("policyholder.validation.contribution_plan_bundle_not_found") % {'id': contribution_plan_bundle_id})
        return bundle

    @classmethod
    def location(cls, user, location_id):
        """A policy holder may only be placed in a location of the author's districts."""
        if not location_id or not settings.ROW_SECURITY:
            return
        from location.apps import LocationConfig
        from location.models import Location
        if LocationConfig.no_location_check or getattr(user, "is_imis_admin", False):
            return
        allowed = Location.objects.filter(id=location_id).filter(
            *PolicyHolder.filter_location(user, paths=("id",), loc_types=('R', 'D', 'W', 'V'), prefix=""))
        if not allowed.exists():
            raise PermissionDenied(_("unauthorized"))

    @classmethod
    def linked_user(cls, user, user_id):
        """
        Linking a user to a policy holder grants them its portal scope: nobody links
        themselves (but an administrator), and the user linked must exist.
        """
        from core.models import User
        if not user_id:
            return
        if str(user_id) == str(user.id) and not getattr(user, "is_imis_admin", False):
            raise PermissionDenied(_("policyholder.validation.cannot_link_oneself"))
        if not User.objects.filter(id=user_id).exists():
            raise ValidationError(_("policyholder.validation.user_not_found") % {'id': user_id})

    @classmethod
    def validate_links(cls, user, data, insuree=False, bundle=False, linked_user=False):
        """The policy holder / insuree / bundle / user `data` names, when it names them."""
        if 'policy_holder_id' in data and data['policy_holder_id'] is not None:
            cls.policy_holder(user, data['policy_holder_id'])
        if insuree and data.get('insuree_id') is not None:
            cls.insuree(user, data['insuree_id'])
        if bundle and data.get('contribution_plan_bundle_id') is not None:
            cls.contribution_plan_bundle(data['contribution_plan_bundle_id'])
        if linked_user and data.get('user_id') is not None:
            cls.linked_user(user, data['user_id'])
