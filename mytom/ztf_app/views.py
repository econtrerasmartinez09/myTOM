import requests
from requests.auth import HTTPBasicAuth

import io
import os
import subprocess
import time
import csv
import requests
import sys
import numpy as np

from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect

from django.forms import HiddenInput
from django.template import loader
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.conf import settings
from django.views.generic import RedirectView, TemplateView, View
from django.views.generic.edit import CreateView, UpdateView, DeleteView, FormMixin
from django.views.generic.detail import DetailView
from django.views.generic import FormView
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy, reverse
from asgiref.sync import sync_to_async

from io import StringIO
from datetime import datetime

from guardian.mixins import PermissionRequiredMixin

from tom_targets.models import Target, TargetList
from tom_common.mixins import Raise403PermissionRequiredMixin


from .forms import ZTFQueryForm
# from .ztf_data_processor import run_data_processor

# Create your views here.

class TargetDetailView(Raise403PermissionRequiredMixin, DetailView):
    permission_required = 'tom_targets.view_target'
    model = Target  # importing Target from ORM

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        # observation_template_form = ApplyObservationTemplateForm(initial={'target': self.get_object()})
        if any(self.request.GET.get(x) for x in ['observation_template', 'cadence_strategy', 'cadence_frequency']):
            initial = {'target': self.object}
            initial.update(self.request.GET)
        # observation_template_form = ApplyObservationTemplateForm(
        # 	initial=initial
        # )
        observation_template_form.fields['target'].widget = HiddenInput()
        context['observation_template_form'] = observation_template_form
        return context

    def get(self, request, *args, **kwargs):
        update_status = request.GET.get('update_status', False)
        if update_status:
            if not request.user.is_authenticated:
                return redirect(reverse('login'))
            target_id = kwargs.get('pk', None)  # key detail that will get the target
            out = StringIO()
            call_command('updatestatus', target_id=target_id, stdout=out)
            messages.info(request, out.getvalue())
            add_hint(request, mark_safe(
                'Did you know updating observation statuses can be automated? Learn how in'
                '<a href=https://tom-toolkit.readthedocs.io/en/stable/customization/automation.html>'
                ' the docs.</a>'))
            return redirect(reverse('tom_targets:detail', args=(target_id,)))

        obs_template_form = ApplyObservationTemplateForm(request.GET)
        if obs_template_form.is_valid():
            obs_template = ObservationTemplate.objects.get(pk=obs_template_form.cleaned_data['observation_template'].id)
            obs_tempalte_params = obs_template.parameters
            obs_tempalte_params['cadence_strategy'] = request.GET.get('cadence_strategy', '')
            obs_tempalte_params['cadence_frequency'] = request.GET.get('cadency_frequency', '')
            params = urlencode(obs_tempalte_params)
            return redirect(
                reverse('tom_observation:create',
                        args=(obs_template.facility,)) + f'?target_id={self.get_object().id}&' + params)

        return super().get(request, *args, **kwargs)


class ZTFQueryView(View):

    def get(self, request, pk, *args, **kwargs):
        target = Target.objects.get(pk=pk)
        context = {
            'target': target,
            'form': ZTFQueryForm,
        }
        return render(request, 'ztf_query.html', context)

    def post(self, request, pk, *args, **kwargs):

        form = ZTFQueryForm(request.POST)
        target = Target.objects.get(pk=pk)

        if form.is_valid():
            print(f"This is the StartMJD: {form.cleaned_data['StartMJD']}")
            print(f"This is the EndMJD: {form.cleaned_data['EndMJD']}")
            ztf_main_func(self, target, StartJD=form.cleaned_data['StartMJD'], EndJD=form.cleaned_data['EndMJD'])
            messages.info(request, "ZTF Query was successful! Please check your email address for data files to be inserted into 'Manage Data' tab of your TOM toolkit.")
            return HttpResponseRedirect(reverse('tom_targets:detail', args=[pk]))
        else:
            form = ZTFQueryForm()

        return render('ztf_query.html', {
            'form': form,
        })

def ztf_main_func(self, target, StartJD, EndJD):

    USER = settings.BROKERS['ztf']['USER']
    PWD = settings.BROKERS['ztf']['PASS']

    print(f"This is the username: {USER}")
    print(f"This is the password: {PWD}")

    print(f"This is the target RA: {target.ra}")
    print(f"This is the target Dec: {target.dec}")

    url = f"https://ztfweb.ipac.caltech.edu/cgi-bin/requestForcedPhotometry.cgi?ra={target.ra}&dec={target.dec}&jdstart={StartJD}&jdend={EndJD}&email={USER}&userpass={PWD}"

    x = requests.get(url, auth=HTTPBasicAuth('ztffps', 'dontgocrazy!'))

    print(x.text)

    return print("Please check your email address for data files to be inserted into 'Manage Data' tab of TOM toolkit for further data processing.")