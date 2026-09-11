"""Thin presentation controller for AQR-015 guided onboarding."""

from . import onboarding_surface_application as _onboarding


class LocalOnboardingController:
    def status(self):
        return _onboarding.get_surface_onboarding()

    def configure(self, payload):
        return _onboarding.configure_surface_onboarding(payload)


__all__ = ["LocalOnboardingController"]
