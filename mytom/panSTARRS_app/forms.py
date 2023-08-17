from django import forms
from tom_targets.models import Target, TargetList


class panstarrsQueryForm(forms.Form):
    Filter = forms.CharField(label='Filter (g,r,i,z,y)')