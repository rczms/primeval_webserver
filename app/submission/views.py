from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseNotFound, Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views import View
from django.core import serializers
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.core.files import File
from django.template.loader import render_to_string
from .models import Run, InputFile, OutputFile, RunLog
from .forms import RunForm, ARVIForm, InputFileForm, OutputFileForm

from background_task import background
from datetime import datetime, timedelta
import base64
import gzip
import io
import re
import os
import pandas as pd
import json
import simplejson
import yaml
import magic
import random
import tarfile
import tempfile

from Bio import SeqIO
import seaborn as sns
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.pyplot as plt
import matplotlib

class UploadView(View):
    def get(self, request):
        # Delete files older than 6 h which are not associated with a run
        time_threshold = datetime.now() - timedelta(hours=6)
        InputFile.objects.filter(run=None, date__lt=time_threshold).delete()

        random_runid = random.randrange(1000000000, 2147483647)
        upload_form = InputFileForm()
        run_form = RunForm(initial={'runID': random_runid})
        run_fields=list(run_form)
        primer_fields, probe_fields, general_fields = run_fields[0:7], run_fields[7:13], run_fields[13:20]
        return render(self.request, 'home.html', {'primer_fields': primer_fields, 'probe_fields': probe_fields, 'general_fields': general_fields, 'runid': random_runid})

    def post(self, request):
        if 'seqtype' in request.POST:
            my_request = self.process_upload(request)
        else:
            my_request = self.process_runform(request)
        return my_request

    def process_upload(self, request):
        form = InputFileForm(self.request.POST, self.request.FILES)
        if form.is_valid():
            upload = form.save(commit=False)

            tmpfile = self.request.FILES['document'].temporary_file_path()
            upload.isAvailable = True
            upload.orig_filename = self.request.FILES['document'].name
            upload.filetype = self.file_type(tmpfile)

            if self.file_ok(tmpfile) == False:
                data = {'upload_is_valid': False, 'upload_error': ["Filetype not supported."]}
            elif upload.seqtype != "mapping" and upload.seqtype != "contig" and self.is_fasta(tmpfile) == False:
                data = {'upload_is_valid': False, 'upload_error': ["File is not valid FASTA format."]}
            elif upload.seqtype != "mapping" and upload.seqtype != "contig" and self.valid_fasta_ids(tmpfile) == False:
                data = {'upload_is_valid': False, 'upload_error': ["Fasta file contains duplicate IDs."]}
            elif upload.seqtype != "mapping" and upload.seqtype != "contig" and self.valid_sequence_lengths(tmpfile, 8) == False:
                data = {'upload_is_valid': False, 'upload_error': ["Fasta file contains sequences < 8 nt."]}
            elif upload.seqtype != "mapping" and upload.seqtype != "contig" and len(upload.orig_filename.rsplit(".", 1)[0]) > 29:
                data = {'upload_is_valid': False, 'upload_error': ["File name length cannot exceed 29 characters."]}
            else:
                upload.save()
                data = {'upload_is_valid': True, 'seqtype': upload.seqtype, 'name': upload.document.name, 'url': upload.document.url, 'upload_error': False}
        else:
            data = {'upload_is_valid': False, 'upload_error': form.errors}
        
        return JsonResponse(data)

    def process_runform(self, request):
        run_form = RunForm(self.request.POST)
        if run_form.is_valid():
            run = run_form.save(commit=False)
            run.createdBy = None

            run.dbs = ",".join(run_form.cleaned_data.get("dbs"))
            
            primers = InputFile.objects.filter(tmpRunID=run.runID,seqtype="primer")
            probes = InputFile.objects.filter(tmpRunID=run.runID,seqtype="probe")
            contigs = InputFile.objects.filter(tmpRunID=run.runID,seqtype="contig")
            mapping = InputFile.objects.filter(tmpRunID=run.runID,seqtype="mapping")

            primer_count,probe_count,contig_count = primers.count(),probes.count(),contigs.count()
            dbs_count = len(run_form.cleaned_data.get("dbs"))
            contig_count += dbs_count

            if run.dbs != "" and run.method != "bowtie":
                data = {'runform_is_valid': False, 'run_form_errors': False, 'other_errors': "You can only select pre-built databases with the Bowtie method."}
            elif contig_count > 0 and (primer_count > 0 or probe_count > 0):
                if primer_count == 0 and run.checkProbesOnly == False:
                    data = {'runform_is_valid': False, 'run_form_errors': False, 'other_errors': "Only probes were uploaded, but option 'checkProbesOnly' is not selected."}
                else:
                    run.save()
                    status = RunLog()
                    status.step= "Submission"
                    status.substep= "Submission"
                    status.running = False
                    status.finished = True
                    status.run = run
                    status.save()
                    newstatus = RunLog()
                    newstatus.step = "Download"
                    newstatus.substep = "Download"
                    newstatus.running = True
                    newstatus.finished = False
                    newstatus.run = run
                    newstatus.save()
                    primers.update(run=run)
                    probes.update(run=run)
                    contigs.update(run=run)
                    mapping.update(run=run)
                    data = {'runform_is_valid': True, 'run_form_errors': False, 'other_errors': False}
            else:
                data = {'runform_is_valid': False, 'run_form_errors': False, 'other_errors': "You have to upload at least primers or probes if 'check probes only' is checked. If you do not select pre-built databases, you have to upload contigs."}
        else:
            data = {'runform_is_valid': False, 'run_form_errors': run_form.errors, 'other_errors': False}
        return JsonResponse(data)

    # Custom functions
    
    def file_type(self, file):
        return magic.from_file(file, mime=True)

    def file_ok(self, file):
        if self.file_type(file) == "text/plain":
            return True
        #elif self.file_type(file) == "application/gzip":
        #    return True
        #elif self.file_type(file) == "application/x-bzip2":
        #    return True
        else:
            return False

    def is_fasta(self, fasta_file):
        sequences = SeqIO.parse(open(fasta_file), "fasta")
        return any(sequences)

    def valid_fasta_ids(self, fasta_file):
        ids = []
        sequences = SeqIO.parse(open(fasta_file), "fasta")
        for fasta in sequences:
            ids.append(fasta.description)
        return len(ids) == len(set(ids))

    def valid_sequence_lengths(self, fasta_file, min_len):
        lens = []
        sequences = SeqIO.parse(open(fasta_file), "fasta")
        for fasta in sequences:
            lens.append(len(str(fasta.seq)))
        return all(x >= min_len for x in lens)

###### ARVI Upload View

class ARVIUploadView(View):
    def get(self, request):
        random_runid = random.randrange(1000000000, 2147483647)
        upload_form = InputFileForm()
        arvi_form = ARVIForm(initial={'runID': random_runid})
        arvi_fields=list(arvi_form)
        return render(self.request, 'arvi.html', {'arvi_fields': arvi_fields, 'runid': random_runid})

    def post(self, request):
        if 'seqtype' in request.POST:
            my_request = self.process_upload(request)
        else:
            my_request = self.process_runform(request)
        return my_request

    def process_upload(self, request):
        form = InputFileForm(self.request.POST, self.request.FILES)
        if form.is_valid():
            upload = form.save(commit=False)

            tmpfile = self.request.FILES['document'].temporary_file_path()
            upload.isAvailable = True
            upload.orig_filename = self.request.FILES['document'].name
            upload.filetype = self.file_type(tmpfile)

            if self.file_ok(tmpfile) == True:
                upload.save()
                data = {'upload_is_valid': True, 'seqtype': upload.seqtype, 'name': upload.document.name, 'url': upload.document.url, 'upload_error': False}
            else:
                data = {'upload_is_valid': False, 'upload_error': ["Filetype not supported."]}
        else:
            data = {'upload_is_valid': False, 'upload_error': form.errors}
        
        return JsonResponse(data)

    def process_runform(self, request):
        arvi_form = ARVIForm(self.request.POST)
        if arvi_form.is_valid():
            run = arvi_form.save(commit=False)
            run.createdBy = None
            run.arvi = True
            run.method = "aho-corasick"
            run.productLength = 1000
            contigs = InputFile.objects.filter(tmpRunID=run.runID,seqtype="contig")
            if contigs.count() > 0:
                run.save()
                
                self.add_file_to_run("/home/vh873400/PRIMEval/PRIMEval/files/maps/abr.fasta", "abr.fasta", "primer", run)
                self.add_file_to_run("/home/vh873400/PRIMEval/PRIMEval/files/maps/vf.fasta", "vf.fasta", "primer", run)
                self.add_file_to_run("/home/vh873400/PRIMEval/PRIMEval/files/maps/abr_probes.fasta", "abr_probes.fasta", "probe", run)
                self.add_file_to_run("/home/vh873400/PRIMEval/PRIMEval/files/maps/vf_probes.fasta", "vf_probes.fasta", "probe", run)
                self.add_file_to_run("/home/vh873400/PRIMEval/PRIMEval/files/maps/abr_map.csv", "abr_map.csv", "mapping", run)
                self.add_file_to_run("/home/vh873400/PRIMEval/PRIMEval/files/maps/vf_map.csv", "vf_map.csv", "mapping", run)

                status = RunLog()
                status.step= "Submission"
                status.substep= "Submission"
                status.running = False
                status.finished = True
                status.run = run
                status.save()
                newstatus = RunLog()
                newstatus.step = "Download"
                newstatus.substep = "Download"
                newstatus.running = True
                newstatus.finished = False
                newstatus.run = run
                newstatus.save()
                contigs.update(run=run)
                data = {'runform_is_valid': True, 'run_form_errors': False, 'other_errors': False}
            else:
                data = {'runform_is_valid': False, 'run_form_errors': False, 'other_errors': "You have to upload contigs."}
        else:
            data = {'runform_is_valid': False, 'run_form_errors': arvi_form.errors, 'other_errors': False}
        return JsonResponse(data)

    def add_file_to_run(self, path, name, seqtype, run):
        nfile = InputFile()
        django_file = File(open(path, "rb"))
        nfile.orig_filename = name
        nfile.seqtype = seqtype
        nfile.filetype = "text/plain"
        nfile.tmpRunID = run.runID
        nfile.run = run
        nfile.document.save(name, django_file, save = True)
        nfile.save()

    # Custom functions
    
    def file_type(self, file):
        return magic.from_file(file, mime=True)

    def file_ok(self, file):
        if self.file_type(file) == "text/plain":
            return True
        #elif self.file_type(file) == "application/gzip":
        #    return True
        #elif self.file_type(file) == "application/x-bzip2":
        #    return True
        else:
            return False

### End of ARVI Upload View

class RunserverDownloadView(View):
    def get(self, request, key):
        my_key = os.environ.get("PRIMEVAL_SERVER_KEY", "defaultkey")
        if key != my_key:
            HttpResponseNotFound()
        else:
            try:
                run = Run.objects.filter(downloaded=False).earliest()
                files = InputFile.objects.filter(run=run, isAvailable=True)

                yaml_settings = yaml.dump({
                    'runID': str(run.runID),
                    'method': str(run.method),
                    'productLength': str(run.productLength),
                    'primerMismatchesTotal': str(run.primerMismatchesTotal),
                    'probeMismatchesTotal': str(run.probeMismatchesTotal),
                    'crossCheck': str(run.crossCheck),
                    'checkProbesOnly': str(run.checkProbesOnly),
                    'dimerCheck': str(run.dimerCheck),
                    'primerMonovalentCations': str(run.primerMonovalentCations),
                    'primerDivalentCations': str(run.primerDivalentCations),
                    'primerDNTPs': str(run.primerDNTPs),
                    'primerConcentration': str(run.primerConcentration),
                    'primerAnnealingTemp': str(run.primerAnnealingTemp),
                    'probeMonovalentCations': str(run.probeMonovalentCations),
                    'probeDivalentCations': str(run.probeDivalentCations),
                    'probeDNTPs': str(run.probeDNTPs),
                    'probeConcentration': str(run.probeConcentration),
                    'probeAnnealingTemp': str(run.probeAnnealingTemp),
                    'dbs': str(run.dbs)
                })
                temp = tempfile.NamedTemporaryFile(mode="w")
                temp.write(yaml_settings)
                temp.flush()

                response = HttpResponse(content_type='application/x-gzip')
                response['Content-Disposition'] = 'attachment; filename=' + str(run.runID) + '.tar'
                tarred = tarfile.open(fileobj=response, mode='w:')
                tarred.add(temp.name, str(run.runID) + "/params.txt")
                
                for doc in files:
                    new_filename = str(doc.orig_filename).replace(" ", "_")
                    if len(new_filename.rsplit(".", 1)) == 1:
                        new_filename = new_filename + ".fasta"
                    new_filename = new_filename.rsplit(".", 1)[0] + ".fasta"
                    tarred.add(doc.document.path, str(run.runID) + "/input/" + str(doc.seqtype) + "s/" + new_filename)
                tarred.close()

                return response
            except Run.DoesNotExist:
                raise Http404("Error retrieving run.")

class RunserverUpdateView(View):
    def get(self, request, key, runid, step, substep, running = 1, finished = 1, error_message = ""):
        my_key = os.environ.get("PRIMEVAL_SERVER_KEY", "defaultkey")
        if key != my_key:
            HttpResponseNotFound()
        else:
            running = True if int(running) == 1 else False
            finished = True if int(finished) == 1 else False
            try:
                # delete files here (because they are not deleted after downloaded but only marked as isAvailable = false
                run = get_object_or_404(Run, runID=runid)
                if step == "Download" and substep == "Download":
                    run.downloaded = True
                    files = InputFile.objects.filter(run=run, isAvailable=True)
                    for doc in files:
                        if doc.seqtype == "contig":
                            doc.isAvailable = False
                            os.remove(doc.document.path)
                            doc.save()
                try:
                    status = RunLog.objects.get(run=run, step=step, substep=substep)
                except:
                    status = RunLog()
                    status.run = run
                    status.step = step
                    status.substep = substep
                # mark run as failed if necessary
                if status.step == "PRIMEval" and status.substep == "Run" and running == 0 and finished == 0:
                    run.failed = True
                status.running = running
                status.finished = finished
                status.error_log = base64.urlsafe_b64decode(error_message).decode()
                status.save()
                run.save()
                return HttpResponse()
            except Run.DoesNotExist:
                return HttpResponseNotFound()

@background(schedule=5)
def create_maps(runid):
    run = Run.objects.get(runID=runid)
    mapping_files = InputFile.objects.filter(run=run, seqtype="mapping").order_by('orig_filename')
    if len(mapping_files) > 0:
        results = OutputFile.objects.get(run=run, isAvailable=True)
        results = pd.read_csv(results.results_wob.path, sep = ";")
        results = results[results['Comment'] != "More than 1 probe binding to amplicon."]
        results.fillna("", inplace=True)
        maps = {}
        for file in mapping_files:
            mapped = pd.read_csv(file.document.path, sep = ";")
            mapped.fillna("", inplace=True)
            columns = list(mapped.columns.values)[5:]
            results_by_sample = {}
            for s in results.groupby("Sequence").groups.items():
                subset1 = pd.merge(results.loc[s[1]], mapped, how = "inner", left_on = ["Primer1", "Primer2", "Probe"], right_on = ["Primer1", "Primer2", "Probe"])
                subset2 = pd.merge(results.loc[s[1]], mapped, how = "inner", left_on = ["Primer1", "Primer2", "Probe"], right_on = ["Primer2", "Primer1", "Probe"])
                subset3 = pd.concat([subset1, subset2], sort = True)
                subset = subset3.sort_values(by = "Gene").to_dict("records")
                results_by_sample[s[0]] = subset
            maps[file.orig_filename] = [results_by_sample, columns]
        run.jsonMaps = simplejson.dumps(maps)
        run.save()

@background(schedule=60)
def send_notification(runid):
    try:
        run = Run.objects.get(runID=runid)
    except:
        return
    if run.email != "":
        subject = "PRIMEval Job " + str(runid) + " finished"
        html_message = render_to_string("email_notification.html", {'runid': str(runid)})
        text_message = "Dear PRIMEval user,\n\nyour job " + str(runid) + " has finished running on the PRIMEval server.\n\nYou can access it by entering the following URL in your browser: " + os.environ.get("BASE_URL", "hostname") + "run/" + str(runid) + "\n\nThank you for using PRIMEval."
        fr = "PRIMEval Webserver <" + os.environ.get("EMAIL_DEFAULT_FROM", "hostmaster@hostname")  + ">"
        to = str(run.email)
        msg = EmailMultiAlternatives(subject, text_message, fr, [to])
        msg.attach_alternative(html_message, "text/html")
        msg.send()

class RunserverUploadView(View):
    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    def post(self, request, key, runid):
        my_key = os.environ.get("PRIMEVAL_SERVER_KEY", "defaultkey")
        if key != my_key:
            HttpResponseNotFound()
        else:
            form = OutputFileForm(self.request.POST, self.request.FILES)
            if form.is_valid():
                try: 
                    run = Run.objects.get(runID=form.cleaned_data['runid'])
                    upload = form.save(commit=False)
                    upload.run = run
                    run.completed = True
                    upload.save()
                    run.save()

                    create_maps(form.cleaned_data['runid'])
                    send_notification(form.cleaned_data['runid'])

                    data = {'upload_is_valid': True}
                except:
                    data = {'upload_is_valid': False, 'upload_error': 'runid does not exist.'}
            else:
                data = {'upload_is_valid': False, 'upload_error': form.errors}
            return JsonResponse(data)


class RunView(View):
    def get(self, request, runid, action):
        try:
            run = Run.objects.get(runID=runid)
        except Run.DoesNotExist:
            return HttpResponseNotFound()

        if run.failed == True:
                try:
                    input_files = InputFile.objects.filter(run=run).order_by('seqtype')
                except InputFile.DoesNotExist:
                    return HttpResponseNotFound()
                return render(self.request, 'run_parameters.html', {'runid': runid, 'arvi': run.arvi, 'run': run, 'files': input_files, 'parameters_active': 'active' })
        elif run.completed == False:
            oligos = "probes" if run.checkProbesOnly == True else "all"
            dimer_check = "dimer_check" if run.dimerCheck == True else "no_dimer_check"
            return render(self.request, 'run_status.html', {'runid': runid, 'method': run.method, 'arvi': run.arvi, 'oligos': oligos, 'dimer_check': dimer_check})
        else:
            if action == "download":
                try:
                    results = OutputFile.objects.get(run=run, isAvailable=True)
                except OutputFile.DoesNotExist:
                    return HttpResponseNotFound()
                return render(self.request, 'run_download.html', {'runid': runid, 'arvi': run.arvi, 'files': results, 'download_active': 'active' })
            if action == "parameters":
                try:
                    input_files = InputFile.objects.filter(run=run).order_by('seqtype')
                except InputFile.DoesNotExist:
                    return HttpResponseNotFound()
                return render(self.request, 'run_parameters.html', {'runid': runid, 'arvi': run.arvi, 'run': run, 'files': input_files, 'parameters_active': 'active' })
            if action == "hits":
                try:
                    results = OutputFile.objects.get(run=run, isAvailable=True)
                except OutputFile.DoesNotExist:
                    return HttpResponseNotFound()
                hits = pd.read_csv(results.hits.path, sep = ";")
                hits.fillna("", inplace=True)
                hits_by_sample = {}
                for s in hits.groupby("Sequence").groups.items():
                    subset = hits.loc[s[1]].to_dict("records")
                    hits_by_sample[s[0]] = subset
                return render(self.request, 'run_hits.html', {'runid': runid, 'arvi': run.arvi, 'results': hits_by_sample, 'hits_active': 'active'})
            if action == "results":
                try:
                    results = OutputFile.objects.get(run=run, isAvailable=True)
                except OutputFile.DoesNotExist:
                    return HttpResponseNotFound()
                # workaround for ARVI - display maps instead of results (which is default if action = "" as defined in urls.py)
                # copy paste of action == "map" section
                if run.arvi == True:
                    mapData = "" if run.jsonMaps == None else run.jsonMaps
                    mapping_files = InputFile.objects.filter(run=run, seqtype="mapping").order_by('orig_filename')
                    if len(mapping_files) > 0 and mapData == "":
                        inProgress = True
                        maps = []
                    elif len(mapping_files) == 0 and mapData == "":
                        inProgress = False
                        maps = []
                    else:
                        inProgress = False
                        maps = simplejson.loads(mapData)
                    return render(self.request, 'run_map.html', {'runid': runid, 'arvi': run.arvi, 'maps': maps, 'map_active': 'active', 'inProgress': inProgress })
                # end of workaround
                else:
                    results = pd.read_csv(results.results_wob.path, sep = ";")
                    results.fillna("", inplace=True)
                    results_by_sample = {}
                    for s in results.groupby("Sequence").groups.items():
                        subset = results.loc[s[1]].to_dict("records")
                        results_by_sample[s[0]] = subset
                    return render(self.request, 'run_results.html', {'runid': runid, 'arvi': run.arvi, 'results': results_by_sample, 'results_active': 'active' })
            if action == "map":
                try:
                    results = OutputFile.objects.get(run=run, isAvailable=True)
                except OutputFile.DoesNotExist:
                    return HttpResponseNotFound()
                mapData = "" if run.jsonMaps == None else run.jsonMaps
                mapping_files = InputFile.objects.filter(run=run, seqtype="mapping").order_by('orig_filename')
                if len(mapping_files) > 0 and mapData == "":
                    inProgress = True
                    maps = []
                elif len(mapping_files) == 0 and mapData == "":
                    inProgress = False
                    maps = []
                else:
                    inProgress = False
                    maps = simplejson.loads(mapData)
                return render(self.request, 'run_map.html', {'runid': runid, 'arvi': run.arvi, 'maps': maps, 'map_active': 'active', 'inProgress': inProgress})
            if action == "dimer":
                try:
                    results = OutputFile.objects.get(run=run, isAvailable=True)
                except OutputFile.DoesNotExist:
                    return HttpResponseNotFound()
                if not results.results_dimer:
                    return render(self.request, 'run_dimer.html', {'runid': runid, 'arvi': run.arvi, 'dimer_active': 'active' })
                else:
                    results = pd.read_excel(results.results_dimer.path, sheet_name = None, na_values = "Nan")
                    dimers = {}
                    for key, value in results.items():
                        if 'CD_' in key:
                            name = str.replace(key, "CD_", "")
                            df = pd.melt(value, id_vars = "Primer1", value_vars = list(value.columns[1:]), var_name = "Primer2", value_name="dG")
                            df = df[df.dG <= -9000]
                            dimer_list = []
                            for index, row in df.iterrows():
                                dimer_list.append(row['Primer1'] + " & " + row['Primer2'] + " (deltaG = " + str(round(row['dG']/1000, 1)) + " kcal/mol)")
                            dimers[key] = [name, "Cross-dimer", dimer_list]
                        if 'HP_' in key:
                            name = str.replace(key, "HP_", "")
                            df = value
                            df = df[(df.dG <= -5000) | (df.Tm >= 40)]
                            dimer_list = []
                            for index, row in df.iterrows():
                                dimer_list.append(row['Oligo'] + " (deltaG = " + str(round(row['dG']/1000, 1)) + " kcal/mol, Tm = " + str(round(row['Tm'], 1)) + ")")
                            dimers[key] = [name, "Hairpin", dimer_list]
                    return render(self.request, 'run_dimer.html', {'runid': runid, 'arvi': run.arvi, 'dimers': dimers, 'dimer_active': 'active' })
            if action == "browse":
                try:
                    results = OutputFile.objects.get(run=run, isAvailable=True)
                except OutputFile.DoesNotExist:
                    return HttpResponseNotFound()
                results = pd.read_csv(results.results_all.path, sep = ";")
                files = self.generate_encoded_files(results, run.checkProbesOnly).items()
                return render(self.request, 'run_browse.html', {'runid': runid, 'arvi': run.arvi, 'files': files, 'browse_active': 'active'})
            else:
                return render(self.request, 'run.html', {'runid': runid })

    def generate_encoded_files(self, results, probes_only = False):
        files = {}
        for sequence in results.groupby("Sequence").groups.items():
            corr = 0
            gff_oligos = str("##gff-version 3\n")
            gff_products = str("##gff-version 3\n")
            cytobands = ""
            for parity, contig in enumerate(results.loc[sequence[1]].groupby("Contig").groups.items()):
                subset = results.loc[contig[1]]
                if probes_only == False:
                    min = subset['StartPos1'].min()
                    max = subset['EndPos2'].max()
                else:
                    min = subset['StartPos'].min()
                    max = subset['EndPos'].min()
                length = max - min + 1
                for index, line in subset.iterrows():
                    factor = corr-min+1
                    if probes_only == False:
                        primer_fwd_start, primer_fwd_end = line['StartPos1']+factor, line['EndPos1']+factor
                        gff_oligos += self.gff_line("test", "transcript", int(primer_fwd_start), int(primer_fwd_end), "+", str(line['Primer1']), "#178ae5")
                        primer_rev_start, primer_rev_end = line['StartPos2']+factor, line['EndPos2']+factor
                        gff_oligos += self.gff_line("test", "transcript", int(primer_rev_start), int(primer_rev_end), "-", str(line['Primer2']), "#65621c")
                        product_start, product_end = line['StartPos1']+factor, line['EndPos2']+factor
                        gff_products += self.gff_line("test", "transcript", int(product_start), int(product_end), "+", "Product of " + str(line['Primer1']) + " and " + str(line['Primer2']), ["#af7052", "#9a4b4b"], parity % 2)
                        probe_start, probe_end = line['StartPos3']+factor, line['EndPos3']+factor
                    else:
                        probe_start, probe_end = line['StartPos']+factor, line['EndPos']+factor
                    if probe_start > 0:
                        if probes_only == True:
                            gff_oligos += self.gff_line("test", "transcript", int(probe_start), int(probe_end), "+", str(line['Probe']), ["#28f215", "#0fb200"], parity % 2)
                        else:
                            gff_oligos += self.gff_line("test", "transcript", int(probe_start), int(probe_end), "+", str(line['Probe']), "#28f215")

                cytobands += self.cytoband_line("test", corr, corr+length, "spacer_1", ["gpos50", "gneg"], parity % 2)
                corr += length

            pseudocontig = self.generate_pseudocontig("test", corr)
            contig_enc = self.encode64gzip(pseudocontig)
            cytobands_enc = self.encode64gzip(cytobands)
            gff_oligos_enc = self.encode64gzip(self.remove_duplicates(gff_oligos))
            gff_products_enc = self.encode64gzip(self.remove_duplicates(gff_products))
            files[sequence[0]] = [contig_enc, cytobands_enc, gff_oligos_enc, gff_products_enc]
        return files

    def generate_pseudocontig(self, name, length):
        return ">" + str(name) + "\n" + "N" * int(length)

    def gff_line(self, seqid, type, start, end, strand, id, color, color_n = 0):
        source, score, phase = ".", ".", "."
        if isinstance(color, list) == True:
            color = str(color[0]) if color_n % 2 else str(color[1])
        attributes = "ID=" + str(id) + ";color=" + str(color)
        return "\t".join([seqid, source, type, str(start), str(end), score, strand, phase, attributes]) + "\n"

    def cytoband_line(self, seqid, start, end, name, color, color_n = 0):
        if isinstance(color, list) == True:
            color = str(color[0]) if color_n % 2 else str(color[1])
        attributes = "ID=" + str(id) + ";color=" + str(color)
        return "\t".join([seqid, str(start), str(end), name, color]) + "\n"

    def remove_duplicates(self, lines):
        seen = set()
        answer = []
        for line in lines.splitlines():
            if line not in seen:
                seen.add(line)
                answer.append(line)
        return "\n".join(answer)

    def encode64gzip(self, data):
        out = io.BytesIO()
        with gzip.GzipFile(fileobj = out, mode = "w") as fo:
            fo.write(data.encode())
        return "data:application/gzip;base64," + base64.b64encode(out.getvalue()).decode("utf-8")

    def decode64gzip(self, data):
        in_ = io.BytesIO()
        in_.write(base64.b64decode(data))
        in_.seek(0)
        with gzip.GzipFile(fileobj = in_, mode = "rb") as fo:
            gunzipped_bytes_obj = fo.read()
        return gunzipped_bytes_obj.decode()

class RunStatusJSONView(View):
    def get(self, request, runid):
        try:
            run = Run.objects.get(runID=runid)
            status = RunLog.objects.filter(run=run)
        except Run.DoesNotExist:
            return HttpResponseNotFound()
        json = simplejson.dumps([{'step': o.step, 'substep': o.substep, 'finished': o.finished, 'running': o.running} for o in status])
        return JsonResponse(json, safe = False)

class HeatmapView(View):
    def get(self, request, runid, sheet, dtype):
        try:
            run = Run.objects.get(runID=runid)
        except Run.DoesNotExist:
            return HttpResponseNotFound()
        try:
            results = OutputFile.objects.get(run=run, isAvailable=True)
        except OutputFile.DoesNotExist:
            return HttpResponseNotFound()
        results = pd.read_excel(results.results_dimer.path, sheet_name = None, na_values = "Nan")
        response = HttpResponse(content_type="image/png")
        plt.gcf().clear()
        for key, value in results.items():
            if key == sheet:
                if 'CD_' in key:
                    df = value
                    df.set_index(['Primer1'], inplace = True)
                    df = df[df.columns].astype(float)
                    df.fillna(0, inplace = True)
                    sns.set(font_scale = 0.2)
                    ax = sns.heatmap(df, vmin = -10000, vmax = 2000, cmap='RdBu', center=-6000)
                    for item in ax.get_yticklabels():
                        item.set_rotation(0)
                    for item in ax.get_xticklabels():
                        item.set_rotation(90)

                    f = matplotlib.figure.Figure()
                    FigureCanvasAgg(f)
                    buf = io.BytesIO()
                    plt.savefig(buf, format = "png", dpi=300)
                    plt.close(f)
                    plt.gcf().clear()
                    response = HttpResponse(buf.getvalue(), content_type='image/png')
                else:
                    df = value
                    df.set_index(['Oligo'], inplace = True)
                    if dtype == "dG":
                        df = df.drop(['Package', 'Tm'], axis = 1)
                    else:
                        df = df.drop(['Package', 'dG'], axis = 1)
                    df.fillna(0, inplace = True)

                    sns.set(font_scale = 0.2)
                    if dtype == "dG":
                        ax = sns.heatmap(df, vmin = -10000, vmax = 2000, cmap='RdBu', center=-3000 , square = True)
                    else:
                        ax = sns.heatmap(df, vmin = 20, vmax = 70, cmap='YlOrRd', center=30 , square = True)
                    for item in ax.get_yticklabels():
                        item.set_rotation(0)
                    for item in ax.get_xticklabels():
                        item.set_rotation(90)
                    
                    f = matplotlib.figure.Figure()
                    FigureCanvasAgg(f)
                    buf = io.BytesIO()
                    plt.savefig(buf, format = "png", dpi=300)
                    plt.close(f)
                    plt.gcf().clear()
                    response = HttpResponse(buf.getvalue(), content_type='image/png')
        return response

class HelpView(View):
    def get(self, request):
        return render(self.request, 'help.html')

class ImpressumView(View):
    def get(self, request):
        return render(self.request, 'impressum.html')

