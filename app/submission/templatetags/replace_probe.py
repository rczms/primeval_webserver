from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()

@register.filter
@stringfilter
def replace_probe(package):
    return package.rsplit("_probes", 1)[0]
