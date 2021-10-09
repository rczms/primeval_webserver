from django import template
register = template.Library()

@register.filter
def replace_commas(string):
    try:
        a = string.replace(',', ', ')
    except:
        a = ""
    return a
