from django.contrib import admin
from .models import Run, RunLog, InputFile, OutputFile, Hit
from . import models

# Inline for Run

class InputFileInLine(admin.TabularInline):
    model = models.InputFile
    readonly_fields = ('date',)
    extra = 0

class OutputFileInLine(admin.TabularInline):
    model = models.OutputFile
    readonly_fields = ('date',)
    extra = 0

class RunLogInLine(admin.TabularInline):
    model = models.RunLog
    readonly_fields = ('date',)
    extra = 0

# Registered models in the admin interface

class InputFileAdmin(admin.ModelAdmin):
    readonly_fields = ("date",)

class RunAdmin(admin.ModelAdmin):
    readonly_fields = ("date",)
    inlines = [InputFileInLine, OutputFileInLine, RunLogInLine]

class OutputFileAdmin(admin.ModelAdmin):
    readonly_fields = ("date",)

class RunLogAdmin(admin.ModelAdmin):
    readonly_fields = ("date",)

class HitAdmin(admin.ModelAdmin):
    pass

admin.site.register(Run, RunAdmin)
admin.site.register(Hit, HitAdmin)
admin.site.register(InputFile, InputFileAdmin)
admin.site.register(OutputFile, OutputFileAdmin)
admin.site.register(RunLog, RunLogAdmin)
