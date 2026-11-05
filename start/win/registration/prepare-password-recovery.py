"""Configure the native self-service flow without printing secrets or sending mail."""

from urllib.parse import urlsplit

from authentik.core.models import Application
from authentik.flows.models import Flow, FlowStageBinding
from authentik.lib.config import CONFIG
from authentik.stages.identification.models import IdentificationStage
from authentik.stages.redirect.models import RedirectStage

return_url = globals().get("BILL_RECOVERY_RETURN_URL", "")
application_slug = globals().get("BILL_RECOVERY_APPLICATION_SLUG", "")
target = urlsplit(return_url)
if (
    target.scheme not in ("http", "https")
    or not target.hostname
    or target.username
    or target.password
    or target.query != "recovery=complete"
    or target.fragment
    or target.path != "/login"
    or (
        target.scheme == "http"
        and target.hostname not in ("localhost", "127.0.0.1", "::1")
    )
):
    raise RuntimeError("Configure a trusted KiscoBooks HTTPS URL before enabling recovery.")

flow = Flow.objects.get(slug="bill-self-service-recovery")
application = Application.objects.get(slug=application_slug)
provider = application.get_provider()
authentication_flow = provider.authentication_flow if provider is not None else None
if authentication_flow is None:
    raise RuntimeError("The KiscoBooks provider must have an explicit authentication flow.")
stages = list(
    IdentificationStage.objects.filter(
        pk__in=FlowStageBinding.objects.filter(target=authentication_flow).values_list(
            "stage_id", flat=True
        )
    )
)
if not stages:
    raise RuntimeError("The KiscoBooks authentication flow has no identification stage.")
for stage in stages:
    if stage.recovery_flow_id and stage.recovery_flow.slug not in (
        "bill-self-service-recovery",
        "bill-administrator-recovery",
    ):
        raise RuntimeError(
            "Preserve the existing recovery flow; review before replacing it."
        )

host = str(CONFIG.get("email.host", "")).strip().lower()
sender = str(CONFIG.get("email.from", "")).strip().lower()
configured = bool(
    host
    and host not in ("localhost", "127.0.0.1", "::1")
    and "@" in sender
    and not sender.endswith("@authentik.local")
)
redirect = RedirectStage.objects.get(name="bill-self-service-recovery-return")
redirect.target_static = return_url
redirect.save(update_fields=["target_static"])
for stage in stages:
    stage.recovery_flow = flow if configured else None
    stage.save(update_fields=["recovery_flow"])
# Brand.flow_recovery remains the token-bound administrator flow used by its API.
print("BILL_SELF_SERVICE_RECOVERY_ENABLED=" + ("true" if configured else "false"))
