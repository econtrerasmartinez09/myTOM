# PREAMBLE with necessary libraries

import io
import os
import subprocess
import time
import csv
import requests
import sys
import numpy as np

from django.shortcuts import render,redirect
from django.http import HttpResponse, HttpResponseRedirect

from django.forms import HiddenInput
from django.template import loader
from django.contrib.auth.mixins import LoginRequiredMixin
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

from .models import QueryModel
from .forms import QueryForm
from .data_processor import run_data_processor

# Create your views here.

class TargetDetailView(Raise403PermissionRequiredMixin, DetailView):
	permission_required = 'tom_targets.view_target'
	model = Target   # importing Target from ORM

	def get_context_data(self, *args, **kwargs):
		context = super().get_context_data(*args,**kwargs)
		# observation_template_form = ApplyObservationTemplateForm(initial={'target': self.get_object()})
		if any(self.request.GET.get(x) for x in ['observation_template','cadence_strategy','cadence_frequency']):
			initial = {'target': self.object}
			initial.update(self.request.GET)
			# observation_template_form = ApplyObservationTemplateForm(
			# 	initial=initial
			# )
		observation_template_form.fields['target'].widget = HiddenInput()
		context['observation_template_form'] = observation_template_form
		return context

	def get(self, request, *args,**kwargs):
		update_status = request.GET.get('update_status', False)
		if update_status:
			if not request.user.is_authenticated:
				return redirect(reverse('login'))
			target_id = kwargs.get('pk',None)   # key detail that will get the target
			out = StringIO()
			call_command('updatestatus',target_id=target_id,stdout=out)
			messages.info(request,out.getvalue())
			add_hint(request,mark_safe(
				'Did you know updating observation statuses can be automated? Learn how in'
				'<a href=https://tom-toolkit.readthedocs.io/en/stable/customization/automation.html>'
				' the docs.</a>'))
			return redirect(reverse('tom_targets:detail',args=(target_id,)))

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

		return super().get(request,*args,**kwargs)

class QueryView(View):

	def get(self, request, pk, *args, **kwargs):
		target = Target.objects.get(pk=pk)
		context = {
			'target':target,
			'form': QueryForm,
		}
		return render(request, 'query.html', context)

	def post(self, request, pk, *args, **kwargs):

		form = QueryForm(request.POST)
		target = Target.objects.get(pk=pk)

		if form.is_valid():
			print(form.cleaned_data['mjd'])
			main_func(self, target , MJD=form.cleaned_data['mjd'])
			return HttpResponseRedirect(reverse('tom_targets:detail',args=[pk]))
		else:
			form = QueryForm()

		return render('query.html', {
			'form': form,
		})

def main_func(self, target, MJD):

	print('This is the RA:', target.ra)
	print('This is the Dec:', target.dec)

	BASEURL = settings.BROKERS['atlas']['BASEURL']

	print(BASEURL)

	if os.environ.get("ATLASFORCED_SECRET_KEY"):
		token = os.environ.get("ATLASFORCED_SECRET_KEY")
		print("Using stored token")

	else:
		data = {"username": settings.BROKERS['atlas']['USER'],
				"password": settings.BROKERS['atlas']['PASS']}

		resp = requests.post(url=f"{BASEURL}/api-token-auth/", data=data)
		print('this is the resp code: ', resp.status_code)

		if resp.status_code == 200:
			token = resp.json()["token"]
			print(f"Your token is {token}")
			print("Store this by running/adding to your .zshrc file:")
			print(f'export ATLASFORCED_SECRET_KEY="{token}"')
		else:
			raise Exception(f"ERROR {resp.status_code}. {resp.text}") #################
			#sys.exit()   #send error messag to test-dataprocessor

	headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

	task_url = None
	while not task_url:
		with requests.Session() as s:
			resp = s.post(
				f"{BASEURL}/queue/", headers=headers,
				data={"ra":target.ra, "dec": target.dec, "mjd_min": MJD, "send_email": False})

			if resp.status_code == 201:
				task_url = resp.json()["url"]
				print(f"The task url is {task_url}")
			elif resp.status_code == 429:
				message = resp.json()["detail"]
				print(f"{resp.status_code} {message}")
				t_sec = re.findall(r"available in (\d+) seconds", message)
				t_min = re.findall(r"available in (\d+) minutes", message)
				if t_sec:
					waittime = int(t_sec[0])
				elif t_min:
					waittime = int(t_min[0]) * 60
				else:
					waittime = 10
				print(f"Waiting {waittime} seconds")
				time.sleep(waittime)
			else:
				raise Exception(f"ERROR {resp.status_code}. {resp.text}")   ##############
				#sys.exit()

	result_url = None
	taskstarted_printed = False
	while not result_url:
		with requests.Session() as s:
			resp = s.get(task_url, headers=headers)

			if resp.status_code == 200:
				if resp.json()["finishtimestamp"]:
					result_url = resp.json()["result_url"]  # PART WHEN QUERY IS COMPLETE
					print(f"Task is complete with results available at {result_url}")
				elif resp.json()["starttimestamp"]:
					if not taskstarted_printed:
						print(f"Task is running (started at {resp.json()['starttimestamp']})")
						taskstarted_printed = True
					time.sleep(2)
				else:
					print(f"Waiting for job to start (queued at {resp.json()['timestamp']})")
					time.sleep(4)
			else:
				raise Exception(f"ERROR {resp.status_code}. {resp.text}") ###################
				#sys.exit()

	with requests.Session() as s:
		textdata = s.get(result_url, headers=headers).text

	file = StringIO(textdata)   # this is KEY for it 'textdata' to be read as a file

	data = []

	for index, line in enumerate(file):
		entries = line.replace("\n", "").split()

		line_data = []

		for idx, x in enumerate(entries):
			if index == 0:  # only for the first line of file (i.e. headers)
				if idx == 0:
					x = x.replace("###", "")
				if idx == 0 or idx == 1 or idx == 2 or idx == 5:   # calls for only MJD, m, dm, F headers
					line_data.append(str(x))
			elif idx == 0 or idx == 5:
				line_data.append(str(x))   # mjd & filter code = str
			elif idx == 1 or idx == 2:
				line_data.append(float(x))   # m & dm = float
		data.append(line_data)

	run_data_processor(data, target)   # custom data processor for ATLAS photometry

	return True

