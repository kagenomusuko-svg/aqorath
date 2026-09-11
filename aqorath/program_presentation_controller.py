"""Thin presentation adapter for OSC Program management."""

from . import program_surface_application as _programs


class ProgramPresentationController:
    def programs(self):
        return _programs.list_program_surface()

    def create_program(self, payload):
        return _programs.create_program_surface(payload)


__all__ = ["ProgramPresentationController"]
