from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.assets.transfer import TransferError, export_assets, import_assets


def _require_transfer_access(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_super_user_role:
            return redirect("accounts:dashboard")
        return view_func(request, *args, **kwargs)

    return wrapper


def _safe_next(request) -> str:
    target = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return "accounts:security_logs"


@_require_transfer_access
def export_data(request):
    payload = export_assets()
    response = HttpResponse(payload, content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="asset-tracking-export.zip"'
    return response


@_require_transfer_access
@require_POST
def import_data(request):
    upload = request.FILES.get("import_file")
    if upload is None:
        messages.error(request, "Choose an export file to import.")
        return redirect(_safe_next(request))
    try:
        result = import_assets(upload)
    except TransferError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Added {result.added} assets. Skipped {result.skipped} already on this copy.",
        )
    return redirect(_safe_next(request))
