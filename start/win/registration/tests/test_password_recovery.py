"""Read-only provider checks. Run with Authentik's `ak shell`; no email or user writes."""

import secrets
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from authentik.brands.models import Brand
from authentik.core.models import User
from authentik.flows.markers import ReevaluateMarker
from authentik.flows.models import Flow, FlowStageBinding
from authentik.flows.planner import (
    PLAN_CONTEXT_IS_RESTORED,
    PLAN_CONTEXT_PENDING_USER,
    FlowNonApplicableException,
    FlowPlanner,
)
from authentik.flows.stage import PLAN_CONTEXT_PENDING_USER_IDENTIFIER
from authentik.lib.config import CONFIG
from authentik.policies.expression.evaluator import PolicyEvaluator
from authentik.policies.expression.models import ExpressionPolicy
from authentik.policies.types import PolicyRequest
from authentik.stages.prompt.stage import PLAN_CONTEXT_PROMPT
from authentik.stages.email.models import EmailStage
from authentik.stages.email.stage import EmailStageView

PREFIX = "bill-self-service-recovery-"


class NativePasswordRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.password = secrets.token_urlsafe(24)
        self.user = User(
            pk=-99999,
            username="unsaved-recovery-review",
            email="review@example.invalid",
            path="bill/pending-registration",
            type="external",
            is_active=True,
            attributes={"billing_email_verified": True},
            password=make_password(self.password),
        )
        self.http = RequestFactory().get("/if/flow/bill-self-service-recovery/")
        self.http.user = AnonymousUser()
        self.http.session = SessionStore()
        self.http._messages = FallbackStorage(self.http)
        self.http.brand = Brand.objects.get(default=True)
        self.plan = SimpleNamespace(
            context={
                PLAN_CONTEXT_PENDING_USER: self.user,
                PLAN_CONTEXT_PENDING_USER_IDENTIFIER: self.user.email,
            }
        )

    def evaluate(self, name, extra=None):
        request = PolicyRequest(AnonymousUser())
        request.set_http_request(self.http)
        request.debug = True
        request.context.update(self.plan.context)
        request.context["flow_plan"] = self.plan
        request.context.update(extra or {})
        evaluator = PolicyEvaluator("read-only-recovery-review")
        evaluator.set_policy_request(request)
        return evaluator.evaluate(
            ExpressionPolicy.objects.get(name=PREFIX + name).expression
        ).passing

    def query(self, user, count=1):
        return patch.object(
            User.objects,
            "filter",
            return_value=SimpleNamespace(first=lambda: user, count=lambda: count),
        )

    def smtp(self):
        return patch.object(
            CONFIG,
            "get",
            side_effect=lambda key, default=None: {
                "email.host": "smtp.example.invalid",
                "email.from": "noreply@example.invalid",
            }.get(key, default),
        )

    def token(self):
        self.plan.context[PLAN_CONTEXT_IS_RESTORED] = SimpleNamespace(
            user_id=self.user.pk,
            flow=SimpleNamespace(slug="bill-self-service-recovery"),
            is_expired=False,
        )

    def test_smtp_is_required_at_the_flow_and_email_boundary(self):
        with patch.object(CONFIG, "get", return_value=""):
            self.assertFalse(self.evaluate("mail-ready"))
            self.assertFalse(self.evaluate("request"))
        with (
            self.smtp(),
            patch("django.core.cache.cache.add"),
            patch("django.core.cache.cache.incr", return_value=1),
            self.query(self.user),
        ):
            self.assertTrue(self.evaluate("mail-ready"))
            self.assertTrue(self.evaluate("request"))

    def test_native_flow_planner_denies_unconfigured_recovery(self):
        planner = FlowPlanner(Flow.objects.get(slug="bill-self-service-recovery"))
        planner.use_cache = False
        with (
            patch.object(CONFIG, "get", return_value=""),
            self.assertRaises(FlowNonApplicableException),
        ):
            planner.plan(self.http, {})

    def test_provider_group_or_role_membership_cannot_authorize_password_write(self):
        self.token()
        for manager in (self.user.groups, self.user.roles):
            with (
                self.subTest(manager=type(manager).__name__),
                self.query(self.user),
                patch.object(type(manager), "exists", return_value=True),
            ):
                self.assertFalse(self.evaluate("proof"))

    def test_requests_normalize_eligible_users_without_displaying_matched_accounts(
        self,
    ):
        with (
            self.smtp(),
            patch("django.core.cache.cache.add"),
            patch("django.core.cache.cache.incr", return_value=1),
            self.query(self.user),
        ):
            self.assertTrue(self.evaluate("request"))
            self.assertEqual(
                self.plan.context[PLAN_CONTEXT_PENDING_USER].pk, self.user.pk
            )

    def test_unknown_inactive_privileged_unverified_passwordless_and_ambiguous_accounts_are_indistinguishable(
        self,
    ):
        for variant in (
            "missing",
            "inactive",
            "internal",
            "service_account",
            "privileged",
            "unverified",
            "passwordless",
            "ambiguous",
        ):
            with self.subTest(variant=variant):
                fresh = User(
                    pk=-88888,
                    username="unsaved-review",
                    email=self.user.email,
                    path=self.user.path,
                    type="external",
                    is_active=True,
                    attributes={"billing_email_verified": True},
                    password=self.user.password,
                )
                if variant == "inactive":
                    fresh.is_active = False
                if variant in ("internal", "service_account"):
                    fresh.type = variant
                if variant == "privileged":
                    fresh.is_superuser = True
                if variant == "unverified":
                    fresh.attributes = {}
                if variant == "passwordless":
                    fresh.password = "!"
                with (
                    self.smtp(),
                    patch("django.core.cache.cache.add"),
                    patch("django.core.cache.cache.incr", return_value=1),
                    self.query(
                        None if variant == "missing" else fresh,
                        count=2 if variant == "ambiguous" else 1,
                    ),
                ):
                    self.assertTrue(self.evaluate("request"))
                    self.assertIsNone(self.plan.context[PLAN_CONTEXT_PENDING_USER].pk)

    def test_native_email_stage_does_not_issue_tokens_or_send_mail_for_a_hidden_account(
        self,
    ):
        self.plan.context[PLAN_CONTEXT_PENDING_USER] = User(
            username=self.user.email, email=self.user.email
        )
        view = object.__new__(EmailStageView)
        view.executor = SimpleNamespace(
            plan=self.plan,
            request=self.http,
            flow=Flow.objects.get(slug="bill-self-service-recovery"),
            current_stage=EmailStage.objects.get(name=PREFIX + "email"),
        )
        with (
            patch.object(view, "get_token") as token,
            patch("authentik.stages.email.stage.send_mails") as mail,
        ):
            view.send_email()
            token.assert_not_called()
            mail.assert_not_called()

    def test_initial_sends_are_limited_across_sessions(self):
        with (
            self.smtp(),
            patch("django.core.cache.cache.add"),
            patch("django.core.cache.cache.incr", return_value=6),
        ):
            self.assertFalse(self.evaluate("request"))
            self.assertIn("five minutes", self.plan.context["deny_message"])

    def test_invalid_email_cannot_start_delivery(self):
        self.plan.context[PLAN_CONTEXT_PENDING_USER_IDENTIFIER] = "invalid"
        with self.smtp():
            self.assertFalse(self.evaluate("request"))

    def test_an_identifier_alone_cannot_authorize_mfa_or_password_write(self):
        with self.query(self.user):
            self.assertFalse(self.evaluate("proof"))

    def test_email_proof_is_bound_to_the_same_user_flow_and_expiry(self):
        self.token()
        with self.query(self.user):
            self.assertTrue(self.evaluate("proof"))
            token = self.plan.context[PLAN_CONTEXT_IS_RESTORED]
            token.user_id = -1
            self.assertFalse(self.evaluate("proof"))
            token.user_id = self.user.pk
            token.flow.slug = "bill-administrator-recovery"
            self.assertFalse(self.evaluate("proof"))
            token.flow.slug = "bill-self-service-recovery"
            token.is_expired = True
            self.assertFalse(self.evaluate("proof"))

    def test_deactivation_or_email_change_after_delivery_denies_write(self):
        self.token()
        fresh = User(
            pk=self.user.pk,
            username=self.user.username,
            email="changed@example.invalid",
            path=self.user.path,
            type=self.user.type,
            is_active=True,
            attributes=self.user.attributes,
            password=self.user.password,
        )
        with self.query(fresh):
            self.assertFalse(self.evaluate("proof"))
            fresh.email = self.user.email
            fresh.is_active = False
            self.assertFalse(self.evaluate("proof"))

    def test_password_validation_uses_the_pending_user_and_rejects_extra_fields(self):
        next_password = secrets.token_urlsafe(24)
        valid = {"password": next_password, "password_repeat": next_password}
        self.assertTrue(self.evaluate("validation", {"prompt_data": valid}))
        for data in (
            {"password": "short", "password_repeat": "short"},
            {"password": next_password, "password_repeat": "different"},
            {"password": self.password, "password_repeat": self.password},
            {**valid, "is_active": True},
            {"password": "x" * 129, "password_repeat": "x" * 129},
        ):
            self.assertFalse(self.evaluate("validation", {"prompt_data": data}))

    def test_deny_stages_stop_invalid_proof_instead_of_skipping_security_checks(self):
        flow = Flow.objects.get(slug="bill-self-service-recovery")
        for order in (25, 45):
            binding = FlowStageBinding.objects.get(target=flow, order=order)
            self.assertEqual(binding.stage.name, PREFIX + "denied")
            self.assertFalse(binding.evaluate_on_plan)
            self.assertTrue(binding.re_evaluate_policies)
            with self.query(self.user):
                self.assertIsNotNone(
                    ReevaluateMarker(binding).process(self.plan, binding, self.http)
                )
                self.token()
                self.assertIsNone(
                    ReevaluateMarker(binding).process(self.plan, binding, self.http)
                )
                self.plan.context.pop(PLAN_CONTEXT_IS_RESTORED)

    def test_false_success_is_denied_without_a_completed_password_write(self):
        with self.query(self.user):
            self.assertFalse(self.evaluate("completed"))
            self.plan.context[PLAN_CONTEXT_PROMPT] = {
                "password": secrets.token_urlsafe(24)
            }
            self.assertFalse(self.evaluate("completed"))
            self.plan.context[PLAN_CONTEXT_PROMPT] = {"password": self.password}
            self.assertTrue(self.evaluate("completed"))

    def test_native_bindings_preserve_admin_recovery_mfa_and_never_create_users(self):
        flow = Flow.objects.get(slug="bill-self-service-recovery")
        self.assertEqual(
            Brand.objects.get(default=True).flow_recovery.slug,
            "bill-administrator-recovery",
        )
        stages = [
            b.stage
            for b in FlowStageBinding.objects.filter(target=flow).order_by("order")
        ]
        identify = stages[0]
        self.assertEqual(identify.user_fields, ["email"])
        self.assertFalse(identify.show_matched_user)
        self.assertTrue(identify.pretend_user_exists)
        email = stages[1]
        self.assertFalse(email.activate_user_on_success)
        self.assertEqual(email.token_expiry, "minutes=9")
        self.assertEqual(email.recovery_max_attempts, 5)
        mfa = next(
            s for s in stages if s.__class__.__name__ == "AuthenticatorValidateStage"
        )
        self.assertEqual(mfa.last_auth_threshold, "seconds=0")
        self.assertEqual(
            next(
                s for s in stages if hasattr(s, "user_creation_mode")
            ).user_creation_mode,
            "never_create",
        )
        self.assertFalse(any(s.__class__.__name__ == "UserLoginStage" for s in stages))
        self.assertTrue(stages[-1].target_static.endswith("/login?recovery=complete"))
        source = Path("/blueprints/custom/bill-self-service-recovery.yaml").read_text()
        self.assertNotIn("__BILL_RECOVERY_RETURN_URL__", source)
        self.assertIn('target_static: "' + stages[-1].target_static + '"', source)
        confirmation = FlowStageBinding.objects.get(target=flow, order=57).stage
        self.assertEqual(confirmation.fields.first().label, "Password reset complete")


suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativePasswordRecoveryTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise RuntimeError("Native password recovery checks failed.")
print(
    "Native recovery checks passed; no user/password/token writes or emails were performed."
)
