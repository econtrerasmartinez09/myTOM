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

#from .models import QueryModel
from .forms import panstarrsQueryForm
from .panstarrs_data_processor import run_data_processor

from astropy.table import Table
from astropy.io import fits


# Create your views here.

ps1filename = "https://ps1images.stsci.edu/cgi-bin/ps1filenames.py"
fitscut = "https://ps1images.stsci.edu/cgi-bin/fitscut.cgi"

class TargetDetailView(Raise403PermissionRequiredMixin, DetailView):
    """
    View that handles the display of the target details. Requires authorization.
    """
    permission_required = 'tom_targets.view_target'
    model = Target

    def get_context_data(self, *args, **kwargs):
        """
        Adds the ``DataProductUploadForm`` to the context and prepopulates the hidden fields.

        :returns: context object
        :rtype: dict
        """
        context = super().get_context_data(*args, **kwargs)
        observation_template_form = ApplyObservationTemplateForm(initial={'target': self.get_object()})
        if any(self.request.GET.get(x) for x in ['observation_template', 'cadence_strategy', 'cadence_frequency']):
            initial = {'target': self.object}
            initial.update(self.request.GET)
            observation_template_form = ApplyObservationTemplateForm(
                initial=initial
            )
        observation_template_form.fields['target'].widget = HiddenInput()
        context['observation_template_form'] = observation_template_form
        return context

    def get(self, request, *args, **kwargs):
        """
        Handles the GET requests to this view. If update_status is passed into the query parameters, calls the
        updatestatus management command to query for new statuses for ``ObservationRecord`` objects associated with this
        target.

        :param request: the request object passed to this view
        :type request: HTTPRequest
        """
        update_status = request.GET.get('update_status', False)
        if update_status:
            if not request.user.is_authenticated:
                return redirect(reverse('login'))
            target_id = kwargs.get('pk', None)
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
            obs_template_params = obs_template.parameters
            obs_template_params['cadence_strategy'] = request.GET.get('cadence_strategy', '')
            obs_template_params['cadence_frequency'] = request.GET.get('cadence_frequency', '')
            params = urlencode(obs_template_params)
            return redirect(
                reverse('tom_observations:create',
                        args=(obs_template.facility,)) + f'?target_id={self.get_object().id}&' + params)

        return super().get(request, *args, **kwargs)

###################################################################################

class PanStarrsQueryView(View):

    def get(self, request, pk, *args, **kwargs):
        target = Target.objects.get(pk=pk)
        context = {
            'target': target,
            'form': panstarrsQueryForm,
        }
        return render(request, 'panstarrs_query.html', context)

    def post(self, request, pk, *args, **kwargs):

        form = panstarrsQueryForm(request.POST)
        target = Target.objects.get(pk=pk)

        if form.is_valid():
            print(f"This is the Filter: {form.cleaned_data['Filter']}")
            panstarrs_main_func(self, target, Filter=form.cleaned_data['Filter'])
            return HttpResponseRedirect(reverse('tom_targets:detail', args=[pk]))
        else:
            form = panstarrsQueryForm()

        return render('panstarrs_query.html', {
            'form': form,
        })

#########################################################################################

def getimages(tra, tdec, size=240, filters="grizy", format="fits", imagetypes="stack"):
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


def panstarrs_main_func(self, target, Filter):
    t0 = time.time()

    tdec = []
    tra = []

    # create a test set of image positions
    # currently setup for a single target

    tdec = np.append(tdec, target.dec)   # collects ra and dec from TOM ORM
    tra = np.append(tra, target.ra)

    # add filter to user input

    # get the PS1 info for those positions
    table = getimages(tra, tdec, filters=Filter)   # inputs the user's choice of filter
    print("{:.1f} s: got list of {} images for {} positions".format(time.time() - t0, len(table), len(tra)))

    # if you are extracting images that are close together on the sky,
    # sorting by skycell and filter will improve the performance because it takes
    # advantage of file system caching on the server
    table.sort(['projcell', 'subcell', 'filter'])

    #####################



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

        open(fname, "wb").write(r.content)   # change this s.t. it is written to disk

        #data = fits.getdata(fname)
        #header = fits.getheader(fname)

    #print(f"this is the data: {data}")
    #print("")
    #print(f"this is the header: {header}")

    #dataproduct = fits.writeto('dataproduct.fits', data, header, overwrite=True)

    #print(f"this is our dataproduct: {dataproduct}")

    #hdulist = fits.open(fname)

    #print(hdulist.info())
    #print("")
    #print(hdulist[0].data)
    #print("")

    #print(f"this is the written fits file: {fname}")

    print(f"We are here right before calling the run data processor!")

    run_data_processor(fname)   # call the run_data_processor