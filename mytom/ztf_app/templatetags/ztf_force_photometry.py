from datetime import datetime, timedelta

from django import template
from django.conf import settings

import logging
from urllib.parse import urlencode

from django import forms
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.shortcuts import reverse
from django.utils import timezone
from guardian.shortcuts import get_objects_for_user
from plotly import offline
import plotly.graph_objs as go
from io import BytesIO
from PIL import Image, ImageDraw
import base64
import numpy as np

from tom_dataproducts.forms import DataProductUploadForm, DataShareForm
from tom_dataproducts.models import DataProduct, ReducedDatum
from tom_dataproducts.processors.data_serializers import SpectrumSerializer
from tom_observations.models import ObservationRecord
from tom_targets.models import Target

from django.db.models import Q

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

register = template.Library()

@register.inclusion_tag('ztf_app/partials/ztf_photometry_buttons.html')   #indexed further back to tempaltes?
def ztf_photometry_buttons(target):
    return {'target': target}

@register.inclusion_tag('tom_dataproducts/partials/photometry_for_target.html', takes_context=True)
def ztf_photometry_for_target(context, target, width=700, height=600, background=None, label_color=None, grid=True):
    """
    Renders a photometric plot for a target.

    This templatetag requires all ``ReducedDatum`` objects with a data_type of ``photometry`` to be structured with the
    following keys in the JSON representation: magnitude, error, filter

    :param width: Width of generated plot
    :type width: int

    :param height: Height of generated plot
    :type width: int

    :param background: Color of the background of generated plot. Can be rgba or hex string.
    :type background: str

    :param label_color: Color of labels/tick labels. Can be rgba or hex string.
    :type label_color: str

    :param grid: Whether to show grid lines.
    :type grid: bool
    """

    color_map = {
        'r': 'red',
        'g': 'green',
        'i': 'black'
    }

    photometry_data = {}
    if settings.TARGET_PERMISSIONS_ONLY:
        print(f"got to the datums filter")
        datums = ReducedDatum.objects.filter(Q(target=target, data_type=settings.DATA_PRODUCT_TYPES['photometry'][0]) | Q(target=target, data_type=settings.DATA_PRODUCT_TYPES['text_file'][0]))
    else:
        datums = get_objects_for_user(context['request'].user,
                                      'tom_dataproducts.view_reduceddatum', Q(
                                      klass=ReducedDatum.objects.filter(
                                        target=target,
                                        data_type=settings.DATA_PRODUCT_TYPES['photometry'][0]))) | Q(target=target, data_type=settings.DATA_PRODUCT_TYPES['text_file'][0])

    for datum in datums:
        photometry_data.setdefault(datum.value['filter'], {})
        photometry_data[datum.value['filter']].setdefault('time', []).append(datum.timestamp)
        photometry_data[datum.value['filter']].setdefault('magnitude', []).append(datum.value.get('magnitude'))
        photometry_data[datum.value['filter']].setdefault('error', []).append(datum.value.get('error'))
        photometry_data[datum.value['filter']].setdefault('limit', []).append(datum.value.get('limit'))

    plot_data = []
    all_ydata = []
    for filter_name, filter_values in photometry_data.items():
        if filter_values['magnitude']:
            series = go.Scatter(
                x=filter_values['time'],
                y=filter_values['magnitude'],
                mode='markers',
                marker=dict(color=color_map.get(filter_name)),
                name=filter_name,
                error_y=dict(
                    type='data',
                    array=filter_values['error'],
                    visible=True
                )
            )
            plot_data.append(series)
            mags = np.array(filter_values['magnitude'], float)  # converts None --> nan (as well as any strings)
            errs = np.array(filter_values['error'], float)
            errs[np.isnan(errs)] = 0.  # missing errors treated as zero
            all_ydata.append(mags + errs)
            all_ydata.append(mags - errs)
        if filter_values['limit']:
            series = go.Scatter(
                x=filter_values['time'],
                y=filter_values['limit'],
                mode='markers',
                opacity=0.5,
                marker=dict(color=color_map.get(filter_name)),
                marker_symbol=6,  # upside down triangle
                name=filter_name + ' non-detection',
            )
            plot_data.append(series)
            all_ydata.append(np.array(filter_values['limit'], float))

    # scale the y-axis manually so that we know the range ahead of time and can scale the secondary y-axis to match
    if all_ydata:
        all_ydata = np.concatenate(all_ydata)
        ymin = np.nanmin(all_ydata)
        ymax = np.nanmax(all_ydata)
        yrange = ymax - ymin
        ymin_view = ymin - 0.05 * yrange
        ymax_view = ymax + 0.05 * yrange
    else:
        ymin_view = 0.
        ymax_view = 0.
    yaxis = {
        'title': 'Apparent Magnitude',
        'range': (ymax_view, ymin_view),
        'showgrid': grid,
        'color': label_color,
        'showline': True,
        'linecolor': label_color,
        'mirror': True,
        'zeroline': False,
    }
    if target.distance is not None:
        dm = 5. * (np.log10(target.distance) - 1.)  # assumes target.distance is in parsecs
        yaxis2 = {
            'title': 'Absolute Magnitude',
            'range': (ymax_view - dm, ymin_view - dm),
            'showgrid': False,
            'overlaying': 'y',
            'side': 'right',
            'zeroline': False,
        }
        plot_data.append(go.Scatter(x=[], y=[], yaxis='y2'))  # dummy data set for abs mag axis
    else:
        yaxis2 = None

    layout = go.Layout(
        xaxis={
            'showgrid': grid,
            'color': label_color,
            'showline': True,
            'linecolor': label_color,
            'mirror': True,
        },
        yaxis=yaxis,
        yaxis2=yaxis2,
        height=height,
        width=width,
        paper_bgcolor=background,
        plot_bgcolor=background,
        legend={
            'font_color': label_color,
            'xanchor': 'center',
            'yanchor': 'bottom',
            'x': 0.5,
            'y': 1.,
            'orientation': 'h',
        },
        clickmode='event+select',
    )
    fig = go.Figure(data=plot_data, layout=layout)

    return {
        'target': target,
        'plot': offline.plot(fig, output_type='div', show_link=False),
    }

@register.inclusion_tag('tom_dataproducts/partials/photometry_datalist_for_target.html', takes_context=True)
def ztf_get_photometry_data(context, target):
    """
    Displays a table of the all photometric points for a target.
    """
    photometry = ReducedDatum.objects.filter(Q(target=target, data_type=settings.DATA_PRODUCT_TYPES['photometry'][0]) | Q(target=target, data_type=settings.DATA_PRODUCT_TYPES['text_file'][0])).order_by('-timestamp')



    # Possibilities for reduced_datums from ZTF/MARS:
    # reduced_datum.value: {'error': 0.0929680392146111, 'filter': 'r', 'magnitude': 18.2364940643311}
    # reduced_datum.value: {'limit': 20.1023998260498, 'filter': 'g'}

    # for limit magnitudes, set the value of the limit key to True and
    # the value of the magnitude key to the limit so the template and
    # treat magnitudes as such and prepend a '>' to the limit magnitudes
    # see recent_photometry.html
    data = []
    for reduced_datum in photometry:
        rd_data = {'id': reduced_datum.pk,
                   'timestamp': reduced_datum.timestamp,
                   'source': reduced_datum.source_name,
                   'filter': reduced_datum.value.get('filter', ''),
                   'telescope': reduced_datum.value.get('telescope', ''),
                   'magnitude_error': reduced_datum.value.get('magnitude_error', '')
                   }

        if 'limit' in reduced_datum.value.keys():
            rd_data['magnitude'] = reduced_datum.value['limit']
            rd_data['limit'] = True
        else:
            rd_data['magnitude'] = reduced_datum.value['magnitude']
            rd_data['limit'] = False
        data.append(rd_data)

    initial = {'submitter': context['request'].user,
               'target': target,
               'data_type': 'photometry',
               'share_title': f"Updated data for {target.name} from {getattr(settings, 'TOM_NAME', 'TOM Toolkit')}.",
               }
    form = DataShareForm(initial=initial)
    form.fields['share_title'].widget = forms.HiddenInput()
    form.fields['data_type'].widget = forms.HiddenInput()

    context = {'data': data,
               'target': target,
               'target_data_share_form': form,
               'sharing_destinations': form.fields['share_destination'].choices}
    return context