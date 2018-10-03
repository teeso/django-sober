from django import template
from django.conf import settings
from django.utils.translation import gettext_lazy as _

register = template.Library()


# to access dict_items beginning with underscores
# useful for debugging
# source: https://stackoverflow.com/a/13694031/333403
@register.filter(name='get')
def get(d, k):
    return d.get(k, None)


@register.filter
def subtract(value, arg):
    return value - arg


@register.filter
def get_info_button_tags(button_type, brick):
    """
    This serves as a global dict-lookup for attributes of the info_button.
    It helps to avoid clumsy or abundant template files

    :param button_type:
    :param brick:
    :return:
    """

    if button_type == "pro":
        res = {"css1": "text-block-button-pro",
               "css3": "bgc_pro1",
               "head1": "pro: {}".format(brick.nbr_pro),
               "head_mo_title": "median vote",
               "head_value": 0,
               }
    elif button_type == "contra":
        res = {"css1": "text-block-button-contra",
               "css3": "bgc_contra1",
               "head1": "contra: {}".format(brick.nbr_contra),
               "head_mo_title": _("median vote"),
               "head_value": 0,
               }
        pass
    else:
        pass

    return res


@register.filter
def settings_value(name):
    """
    This filter serves to access the some values from settings.py inside the templates
    without passing them through the view.

    For security we only allow such values which are explictly mentioned here.
    (to e.g. prevent an adversary template author to access settings.DATABASES etc.)

    :param name:    name of the requested setting
    :return:
    """

    allowed_settings = ["DEBUG"]

    if name not in allowed_settings:
        msg = "using settings.{} is not explicitly allowed".format(name)
        raise ValueError(msg)

    return getattr(settings, name, False)

# maybe a restart of the server is neccessary after chanching this file
