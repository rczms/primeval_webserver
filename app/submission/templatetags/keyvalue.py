from django import template

register = template.Library()

@register.filter
def keyvalue(_1_2, element_no):
    df_entry, columns = _1_2
    element = columns[element_no]
    try:
        return df_entry[element]
    except KeyError:
        return ''

@register.filter
def one_more(_1, _2):
    return _1, _2
