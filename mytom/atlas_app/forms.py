from django import forms

class QueryForm(forms.Form):
	RA  = forms.CharField(label='RA', max_length=100)
	Dec = forms.CharField(label='Dec', max_length=100)
	MJD = forms.CharField(label='MJD', max_length=100)
	Email = forms.CharField(label='Email', max_length=100)
