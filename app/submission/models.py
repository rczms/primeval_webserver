from django.db import models
from django.contrib.auth.models import User
from django.dispatch import receiver

import os

# Create your models here.

# implement validators for permitted values (e.g. not negative, min value, max value, ...)

class Run(models.Model):
    runID                   = models.PositiveIntegerField(unique=True)
    method                  = models.CharField(max_length=100)
    productLength           = models.PositiveIntegerField(default=1500, verbose_name = "Product length (bp)")
    primerMonovalentCations = models.FloatField(default=50, verbose_name = "Monovalent cations (mM)")
    primerDivalentCations   = models.FloatField(default=1.5, verbose_name = "Divalent cations (mM)")
    primerDNTPs             = models.FloatField(default=1.75, verbose_name = "dNTPs (mM)")
    primerConcentration     = models.FloatField(default=300, verbose_name = "Annealing oligo concentration (nM)")
    primerAnnealingTemp     = models.FloatField(default=55, verbose_name = "Primer annealing temperature (°C)")
    probeMonovalentCations  = models.FloatField(default=25, verbose_name = "Monovalent cations (mM)")
    probeDivalentCations    = models.FloatField(default=10, verbose_name = "Divalent cations (mM)")
    probeDNTPs              = models.FloatField(default=0, verbose_name = "dNTPs (mM)")
    probeConcentration      = models.FloatField(default=50, verbose_name = "Probe concentration (nM)")
    probeAnnealingTemp      = models.FloatField(default=70, verbose_name = "Probe annealing temperature (°C)")
    primerMismatchesTotal   = models.PositiveSmallIntegerField(default=0, verbose_name = "Primer mismatches")
    probeMismatchesTotal    = models.PositiveSmallIntegerField(default=0, verbose_name = "Probe mismatches")
    dbs                     = models.CharField(max_length=10000, blank=True, null=True)
    crossCheck              = models.BooleanField(default=False, verbose_name = "Cross-check primer packages")
    dimerCheck              = models.BooleanField(default=False, verbose_name = "Secondary structure check")
    checkProbesOnly         = models.BooleanField(default=False, verbose_name = "Check probes only")
    downloaded              = models.BooleanField(default=False)
    completed               = models.BooleanField(default=False)
    failed                  = models.BooleanField(default=False)
    arvi                    = models.BooleanField(default=False, blank=True)
    email                   = models.EmailField(blank=True, null=True, max_length=254, verbose_name = "Notification email")
    date                    = models.DateTimeField(auto_now_add=True)
    jsonMaps                = models.TextField(blank=True, null=True)
    createdBy               = models.ForeignKey(User, on_delete = models.CASCADE, related_name="runs", blank=True, null=True)
    class Meta:
        get_latest_by = 'date'

class RunLog(models.Model):
    step           = models.CharField(default = "", max_length = 40) 
    substep        = models.CharField(default = "", max_length = 40)
    finished       = models.BooleanField(default=False)
    running        = models.BooleanField(default=False)
    execution_time = models.DurationField(null=True, blank = True)
    error_log      = models.CharField(default = "", blank = True, max_length = 10000)
    date           = models.DateTimeField(auto_now_add=True)
    run            = models.ForeignKey(Run, on_delete = models.CASCADE, related_name="status", blank = True, null = True)
    class Meta:
        get_latest_by = 'date'

class InputFile(models.Model):
    document      = models.FileField(upload_to='')
    orig_filename = models.CharField(max_length=255)
    seqtype       = models.CharField(max_length=64)
    filetype      = models.CharField(max_length=64)
    isAvailable   = models.BooleanField(default=True)
    date          = models.DateTimeField(auto_now_add=True)
    tmpRunID      = models.PositiveIntegerField()
    run           = models.ForeignKey(Run, on_delete = models.CASCADE, related_name="files", blank=True, null=True)

class OutputFile(models.Model):
    hits          = models.FileField(upload_to='')
    results_all   = models.FileField(upload_to='')
    results_wob   = models.FileField(upload_to='')
    results_dimer = models.FileField(upload_to='', blank=True, null=True)
    isAvailable   = models.BooleanField(default=True)
    date          = models.DateTimeField(auto_now_add=True)
    run           = models.ForeignKey(Run, on_delete = models.CASCADE, related_name="results", blank=True, null=True)

class Hit(models.Model):
    sequence        = models.CharField(max_length = 255)
    contig          = models.CharField(max_length = 1000)
    type            = models.CharField(max_length = 50)
    name            = models.CharField(max_length = 255)
    package         = models.CharField(max_length = 255)
    startPos        = models.PositiveIntegerField()
    endPos          = models.PositiveIntegerField()
    mismatchesTotal = models.CharField(max_length = 5)
    strand          = models.PositiveSmallIntegerField()
    hitSequence     = models.TextField()
    run             = models.ForeignKey(Run, on_delete = models.CASCADE, related_name="hit", blank=True, null=True)

class Result(models.Model):
    sequence          = models.CharField(max_length = 255)
    contig            = models.TextField()
    primer1           = models.CharField(max_length = 255)
    primer2           = models.CharField(max_length = 255)
    probe             = models.CharField(max_length = 255)
    primer1Package    = models.CharField(max_length = 255)
    primer2Package    = models.CharField(max_length = 255)
    probePackage      = models.CharField(max_length = 255)
    startPos1         = models.PositiveIntegerField()
    endPos1           = models.PositiveIntegerField()
    startPos2         = models.PositiveIntegerField()
    endPos2           = models.PositiveIntegerField()
    startPos3         = models.PositiveIntegerField()
    endPos3           = models.PositiveIntegerField()
    productSize       = models.PositiveIntegerField()
    noMismatchesLeft  = models.CharField(max_length = 5)
    noMismatchesRight = models.CharField(max_length = 5)
    noMismatchesProbe = models.CharField(max_length = 5)
    mismatchesLeft    = models.CharField(max_length = 255)
    mismatchesRight   = models.CharField(max_length = 255)
    mismatchesProbe   = models.CharField(max_length = 255)
    comment           = models.CharField(max_length = 1000)
    product           = models.TextField()
    run               = models.ForeignKey(Run, on_delete = models.CASCADE, related_name="result", blank=True, null=True)

# Deletes file from filesystem when corresponding `MediaFile` object is deleted.
@receiver(models.signals.post_delete, sender=InputFile)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    if instance.document:
        if os.path.isfile(instance.document.path):
            os.remove(instance.document.path)

# Deletes old file from filesystem when corresponding `MediaFile` object is updated with new file.
@receiver(models.signals.pre_save, sender=InputFile)
def auto_delete_file_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return False
    try:
        old_file = sender.objects.get(pk=instance.pk).document
    except sender.DoesNotExist:
        return False

    new_file = instance.document
    if not old_file == new_file:
        if os.path.isfile(old_file.path):
            os.remove(old_file.path)

