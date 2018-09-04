import collections
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Brick
from .simple_pages import defdict as sp_defdict
from .forms import forms
from .language import lang

from ipydex import IPS

brick_ordering = ['type', 'cached_avg_vote', 'update_datetime']
brick_ordering_chrono = ['type', 'creation_datetime']

template_mapping = {Brick.thesis: "brick_thesis.html",
                    Brick.pro: "brick_pro.html",
                    Brick.contra: "brick_contra.html",
                    Brick.question: "brick_question.html",
                    Brick.comment: "brick_comment.html",
                    }

symbol_mapping = {Brick.thesis: "!",
                  Brick.pro: "✓",
                  Brick.contra: "⚡",
                  Brick.question: "?",
                  Brick.comment: '"',
                 }

assert len(symbol_mapping) == len(Brick.type_names_codes)

# the following solves the problem that adhoc attributes attached to Model instances are not saved in the database
# if the same instance is restrieved later again (e.g. in recursive function calls) the attribute is lost.
# we store it in a dict {(pk, attrname): value}
brick_attr_store = {}

# other approach to same problem: save the processed bricks
processed_bricks = {}

# to avoid that this dict grows over time it should be cleared after usage. This could be done by a decorator.


# empty object to store some attributes at runtime
class Container(object):
    pass


def view_index(request):

    # get a list of all thesis-bricks

    thesis_list = Brick.objects.filter(type=Brick.thesis)

    base_object = Container()
    # !! hcl
    base_object.title = "List of Theses"

    base_object.special_head_link = "new_thesis_link"

    for tbrick in thesis_list:
        tbrick.template = "sober/{}".format(template_mapping.get(tbrick.type))
        tbrick.title_tag = "Thesis#{}".format(tbrick.pk)
    base_object.sorted_child_list = thesis_list

    return render(request, 'sober/main_brick_tree.html', {'base': base_object})
    # return render(request, 'sober/main_simple_page.html', {})


def view_simple_page(request, pagetype=None):
    """
    Render (almost) static page
    :param request:
    :param pagetype:
    :return:
    """

    context = {"pagetype": pagetype, "sp": sp_defdict[pagetype]}
    return render(request, 'sober/main_simple_page.html', context)


def view_renderbrick(request, brick_id=None):
    """
    Top level rendering of a brick

    :param request:
    :param brick_id:
    :return:
    """
    base_brick = get_object_or_404(Brick, pk=brick_id)

    root_parent, rp_level = get_root_parent(base_brick)

    # use this call to process all bricks down to the sibling level
    # !! todo: better document why this is needed
    process_child_bricks(root_parent,
                         root_type=root_parent.type,
                         current_level=0,
                         rp_level=rp_level,
                         max_level=rp_level)

    # this is the call which we mainly need (after the preparation)
    base_brick.sorted_child_list = process_child_bricks(base_brick,
                                                        root_type=base_brick.type,
                                                        rp_level=rp_level,
                                                        current_level=0, max_level=20)

    # let the base know how many childs of each type it has
    base_brick.child_type_counter = brick_attr_store[(base_brick.pk, "child_type_counter")]
    set_child_type_counters(base_brick)

    return render(request, 'sober/main_brick_tree.html', {'base': base_brick})


def view_new_brick(request, brick_id=None, type_code=None):
    """
    create a new brick of a given type (render form)

    :param request:
    :param brick_id:
    :param type_code: one of {th, pa, ca, qu, is}
    :return:
    """

    if type_code not in Brick.typecode_map.keys():
        raise ValueError("Invalid type_code `{}` for Brick".format(type_code))

    sp = Container()
    sp.title = "New {1}-Brick to {0}".format(brick_id, type_code)

    lc = "en"
    sp.long_brick_type = lang[lc]['long_brick_type'][type_code]

    if type_code == Brick.reverse_typecode_map[Brick.thesis]:
        # ensure that we come from the correct url-dispatcher
        assert brick_id == -1
        sp.parent_brick = None

    else:
        sp.parent_brick = prepare_base_brick_for_new_and_edit(brick_id)

    # here we process the submitted form
    if request.method == 'POST':
        brickform = forms.BrickForm(request.POST)

        if not brickform.is_valid():
            # render some error message here
            sp.content = "Errors: {}<br>{}".format(brickform.errors, brickform.non_form_errors)

        else:
            new_brick = brickform.save(commit=False)
            new_brick.parent = sp.parent_brick
            new_brick.type = Brick.typecode_map[type_code]
            new_brick.save()
            sp.content = "no errors. Form saved. Result: {}".format(new_brick)

    # here we handle the generation of an empty form
    else:
        brickform = forms.BrickForm()
        sp.content = ""
        sp.form = brickform

    if hasattr(sp, "form"):
        sp.form.form_type = "new"

        if type_code == Brick.reverse_typecode_map[Brick.thesis]:
            sp.form.action_url_name = "new_thesis"
        else:
            sp.form.action_url_name = "new_brick"

    context = {"pagetype": "FORM-Mockup", "sp": sp, "brick_id": brick_id, "type_code": type_code}
    return render(request, 'sober/main_simple_page.html', context)


def view_edit_brick(request, brick_id=None):
    sp = Container()

    sp.brick_to_edit = prepare_base_brick_for_new_and_edit(brick_id)

    lc = "en"
    type_code = Brick.reverse_typecode_map[sp.brick_to_edit.type]
    sp.long_brick_type = lang[lc]['long_brick_type'][type_code]
    sp.title = "Edit {1}-Brick with {0}".format(brick_id, sp.long_brick_type)

    # here we process the submitted form
    if request.method == 'POST':
        brickform = forms.BrickForm(request.POST, instance=sp.brick_to_edit)

        if not brickform.is_valid():
            # render some error message here
            sp.content = "Errors: {}<br>{}".format(brickform.errors, brickform.non_form_errors)

        else:
            edited_brick = brickform.save(commit=False)
            edited_brick.update_datetime = timezone.now()
            edited_brick.save()
            sp.content = "no errors. Form saved. Result: {}".format(edited_brick)

    # here we handle the generation of an empty form
    else:
        brickform = forms.BrickForm(instance=sp.brick_to_edit)
        sp.content = ""
        sp.form = brickform

    if hasattr(sp, "form"):
        sp.form.form_type = "edit"
        sp.form.action_url_name = "edit_brick"

    context = {"pagetype": "FORM-Mockup", "sp": sp, "brick_id": brick_id, "type_code": None}
    return render(request, 'sober/main_simple_page.html', context)

    pass

# ------------------------------------------------------------------------
# below are auxiliary functions which do not directly produce a view
# ------------------------------------------------------------------------


def prepare_base_brick_for_new_and_edit(brick_id):

    base_brick = get_object_or_404(Brick, pk=brick_id)
    root_parent, rp_level = get_root_parent(base_brick)

    # use this call to process all bricks down to the sibling level of base_brick
    # set template and relative links etc
    process_child_bricks(root_parent,
                         root_type=root_parent.type,
                         current_level=0,
                         rp_level=rp_level,
                         max_level=rp_level)

    return processed_bricks[base_brick.pk]


def process_child_bricks(brick, root_type, rp_level, current_level, max_level):
    """
    This function will be called recursively.
    It sets the
     - absolute_level (w.r.t. the root_parent)
     - relative_level (w.r.t. the base_brick)
     - template
     - title_tag (string)
     of the brick, and looks for childs and processes them.

    Return a flat list containing this brick and all childs up to max_level.

    :param brick:
    :param root_type:       type of the root brick (used for some css selection)
    :param current_level:
    :param max_level:       int (this is for algorithmic safety.) See notes below

    :return: list of bricks (up to max_level)
    """

    # This max_level is for algorithmic safety only. The display threshold is handled via the template.
    if current_level > max_level:
        return []


    brick.relative_level = current_level
    brick.absolute_level = current_level + rp_level

    type_counter = collections.Counter()
    # iterate over all children to fix their chronological order (see the use of typed_idx below)
    for b in brick.children.all().order_by(*brick_ordering_chrono):
        type_counter.update([b.type])
        # e.g. dertermine that this is the 3rd pro-brick on the current level
        brick_attr_store[(b.pk, "typed_idx")] = type_counter[b.type]

    # save the whole counter in the store.
    # this enables us to display how much pro and contra args there are
    brick_attr_store[(brick.pk, "child_type_counter")] = type_counter

    # Indentation (margin-left (ml)) should depend on the current (pseudo-)root
    # this logic could be implemented in the templates
    # but it would look ugly there (due to the lack of real variables)
    if root_type == brick.thesis:
        brick.indentation_class = "ml{}".format(max([0, current_level - 1]))
    else:
        brick.indentation_class = "ml{}".format(current_level)

    # set the template
    brick.template = "sober/{}".format(template_mapping.get(brick.type))

    set_title_tag(brick)

    # now apply this function recursively to all child-bricks
    res = [brick]
    processed_bricks[brick.pk] = brick
    direct_children = brick.children.all().order_by(*brick_ordering)

    for i, b in enumerate(direct_children):
        res.extend(process_child_bricks(b, root_type, rp_level,
                                        current_level + 1, max_level))

    return res


def set_title_tag(brick):
    """
    determine the title tag (something like pro#3⚡2⚡1?3) and the parent_type_list

    :param brick:
    :return: None (changes brick object)
    """

    if brick.parent is None:
        assert brick.type == Brick.thesis
        # other types must have a parent (!! what is with question?)

        brick.parent_type_list = [(Brick.types_map[brick.type]+"#", brick.pk, brick.pk)]
        # this is a list which stores tuples (split_symbol, xxx, pk) for each parent
        # xxx is pk for thesis and typed_idx for other brick_types

    else:
        assert brick.parent is not None

        # this is needed, when we start with a child
        if not hasattr(brick.parent, "title_tag"):
            set_title_tag(brick.parent)

        assert hasattr(brick.parent, "parent_type_list")

        # if brick was the root
        if brick_attr_store.get((brick.pk, "typed_idx")) is None:
            brick_attr_store[(brick.pk, "typed_idx")] = 1

        new_tuple = (symbol_mapping[brick.type], brick_attr_store[(brick.pk, "typed_idx")], brick.pk)
        brick.parent_type_list = brick.parent.parent_type_list + [new_tuple]

        brick.title_tag = create_title_tag(brick.parent_type_list)

    brick.title_tag = create_title_tag(brick.parent_type_list)
    return None


def create_title_tag(parent_type_list):
    res = ""
    for symb, tidx, pk in parent_type_list:
        res += "{}{}".format(symb, tidx)

    return res


def get_root_parent(brick):
    """
    Go upward in child-parent-hierarchy and return that parent-...-parent brick which
    has no parent itself. Also return the number of upward-steps.

    :param brick:
    :return:
    """

    level = 0
    while brick.parent is not None:
        brick = brick.parent
        level += 1

    assert brick.parent is None
    return brick, level


def set_child_type_counters(brick):
    """
    create attributes like brick.child_type_counter_pro (how many pro-childs does this brick have?)

    :param brick:   Brick
    :return:        None
    """

    for key, type_str in Brick.types:
        # get the counter (dict-like object) from the store and evaluate it with the type `key`

        ctc = brick_attr_store[(brick.pk, "child_type_counter")].get(key, 0)

        attr_name = "number_of_childs_{}".format(type_str.lower())
        setattr(brick, attr_name, ctc)
        print("set_ctc:", brick, key, ctc,)
