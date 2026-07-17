from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Usage: {{ some_dict|get_item:some_key }}
    Django templates can't do dict[variable_key] directly — this fills the gap.
    Returns None if the dict or key is missing, rather than raising.
    """
    if not dictionary:
        return None
    return dictionary.get(key)