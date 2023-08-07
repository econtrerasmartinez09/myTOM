from django import forms
from tom_targets.models import Target, TargetList


class ZTFQueryForm(forms.Form):
    StartMJD = forms.FloatField(label='Start JD')
    EndMJD = forms.FloatField(label='End JD')
