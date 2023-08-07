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


class QueryView(View):

    def get(self, request, pk, *args, **kwargs):
        target = Target.objects.get(pk=pk)
        context = {
            'target': target,
            'form': QueryForm,
        }
        return render(request, 'query.html', context)

    def post(self, request, pk, *args, **kwargs):

        form = QueryForm(request.POST)
        target = Target.objects.get(pk=pk)

        if form.is_valid():
            print(form.cleaned_data['mjd'])

            tra = target.ra
            tdec = target.dec

            getimages(self, tra, tdec)
            return HttpResponseRedirect(reverse('tom_targets:detail', args=[pk]))
        else:
            form = QueryForm()

        return render('query.html', {
            'form': form,
        })



ps1filename = "https://ps1images.stsci.edu/cgi-bin/ps1filenames.py"
fitscut = "https://ps1images.stsci.edu/cgi-bin/fitscut.cgi"

def getimages(self, tra, tdec, size=240, filters="grizy", format="fits", imagetypes="stack"):
    """Query ps1filenames.py service for multiple positions to get a list of images
    This adds a url column to the table to retrieve the cutout.

    tra, tdec = list of positions in degrees
    size = image size in pixels (0.25 arcsec/pixel)
    filters = string with filters to include
    format = data format (options are "fits", "jpg", or "png")
    imagetypes = list of any of the acceptable image types.  Default is stack;
        other common choices include warp (single-epoch images), stack.wt (weight image),
        stack.mask, stack.exp (exposure time), stack.num (number of exposures),
        warp.wt, and warp.mask.  This parameter can be a list of strings or a
        comma-separated string.

    Returns an astropy table with the results
    """

    if format not in ("jpg", "png", "fits"):
        raise ValueError("format must be one of jpg, png, fits")
    # if imagetypes is a list, convert to a comma-separated string
    if not isinstance(imagetypes, str):
        imagetypes = ",".join(imagetypes)
    # put the positions in an in-memory file object
    cbuf = StringIO()
    cbuf.write('\n'.join(["{} {}".format(ra, dec) for (ra, dec) in zip(tra, tdec)]))
    cbuf.seek(0)
    # use requests.post to pass in positions as a file
    r = requests.post(ps1filename, data=dict(filters=filters, type=imagetypes),
                      files=dict(file=cbuf))
    r.raise_for_status()
    tab = Table.read(r.text, format="ascii")

    urlbase = "{}?size={}&format={}".format(fitscut, size, format)
    tab["url"] = ["{}&ra={}&dec={}&red={}".format(urlbase, ra, dec, filename)
                  for (filename, ra, dec) in zip(tab["filename"], tab["ra"], tab["dec"])]
    return tab


if __name__ == "__main__":
    t0 = time.time()

    # create a test set of image positions
    tdec = np.append(np.arange(31) * 3.95 - 29.1, 88.0)
    tra = np.append(np.arange(31) * 12., 0.0)

    # get the PS1 info for those positions
    table = getimages(tra, tdec, filters="ri")
    print("{:.1f} s: got list of {} images for {} positions".format(time.time() - t0, len(table), len(tra)))

    # if you are extracting images that are close together on the sky,
    # sorting by skycell and filter will improve the performance because it takes
    # advantage of file system caching on the server
    table.sort(['projcell', 'subcell', 'filter'])

    # extract cutout for each position/filter combination
    for row in table:
        ra = row['ra']
        dec = row['dec']
        projcell = row['projcell']
        subcell = row['subcell']
        filter = row['filter']

        # create a name for the image -- could also include the projection cell or other info
        fname = "t{:08.4f}{:+07.4f}.{}.fits".format(ra, dec, filter)

        url = row["url"]
        print("%11.6f %10.6f skycell.%4.4d.%3.3d %s" % (ra, dec, projcell, subcell, fname))
        r = requests.get(url)
        open(fname, "wb").write(r.content)
    print("{:.1f} s: retrieved {} FITS files for {} positions".format(time.time() - t0, len(table), len(tra)))
