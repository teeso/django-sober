from django.test import TestCase
from django.urls import reverse
from django.core import serializers
from django.conf import settings

from bs4 import BeautifulSoup

from . import model_helpers as mh
from . import utils

from ipydex import IPS
from .models import Brick, User, SettingsBunch

if __name__ == "__main__":
    print("Run tests with `python manage.py test sober.tests.T.ips`")

# todo: setup selenium:
# https://docs.djangoproject.com/en/2.1/topics/testing/tools/#django.test.LiveServerTestCase

# to get the current production data: py3 manage.py dumpdata  sober | jsonlint -f > sober_sample_data.json


global_fixtures = ['for_unit_tests/bricks.json',
                   'for_unit_tests/aux_and_auth_data.json']

default_brick_ordering = ['type', 'cached_avg_vote', 'update_datetime']

global_login_data1 = dict(username='dummy_user', password='karpfenmond')
global_login_data2 = dict(username='dummy_user2', password='karpfenmond')


class DataIntegrityTests(TestCase):
    fixtures = global_fixtures

    def test_fixture_integrity(self):
        self.assertTrue(utils.ensure_data_integrity())

    def test_find_some_childs(self):

        try:
            brick = Brick.objects.get(pk=1)
        except Brick.DoesNotExist:
            success = False
        else:
            success = True

        self.assertTrue(success)

    def test_default_settings_are_not_assigned_to_user(self):

        default_settings = SettingsBunch.objects.get(pk=1)
        users = User.objects.all()

        self.assertNotEqual(len(users), 0)

        for user in users:
            self.assertIsNot(user.soberuser.settings, default_settings)

    def test_settings_bunch_dict(self):

        default_settings = SettingsBunch.objects.get(pk=1)
        d = default_settings.get_dict()

        # actually here the concrete values are not important
        # we only want to have dict-access to them and they should be as expected
        self.assertEqual(d["language"], "en")
        self.assertEqual(d["max_rlevel"], 8)

    def test_settings_logged_in_user(self):
        logged_in = self.client.login(**global_login_data1)
        self.assertTrue(logged_in)

        response = self.client.get(reverse('settings_dialog'))

        form, action_url = get_form_by_action_url(response, "settings_dialog")
        post_data = generate_post_data_for_form(form, spec_values={"language": "de", "max_rlevel": 21})

        response = self.client.post(action_url, post_data)
        self.assertContains(response, "utc_deutsche_sprache_aktiviert")

        settings_dict1 = self.client.session["settings_dict"]

        # assert that the posted settings are now in the session
        self.assertEqual(settings_dict1["max_rlevel"], 21)
        self.assertEqual(settings_dict1["language"], "de")

        # do not use self.client.logout() because it does not copy the settings to the new session
        response = self.client.get(reverse('logout_page'))
        # response = self.client.get(reverse('debug_page'))
        settings_dict2 = self.client.session["settings_dict"]

        self.assertEqual(settings_dict1, settings_dict2)

        # now change the settings while not beeing logged in
        post_data = generate_post_data_for_form(form, spec_values={"language": "es", "max_rlevel": 10})
        response = self.client.post(action_url, post_data)

        settings_dict3 = self.client.session["settings_dict"]
        self.assertEqual(settings_dict3["max_rlevel"], 10)
        self.assertEqual(settings_dict3["language"], "es")

        # login again (but via the view to adapt the session) and assert that we have the saved settings
        # self.client.login(**global_login_data) # this does not w

        login_url = reverse('login_page')
        response = self.client.get(login_url)
        form, _ = get_form_by_action_url(response, None)
        post_data = generate_post_data_for_form(form, spec_values=global_login_data1)
        response = self.client.post(login_url, post_data)

        settings_dict4 = self.client.session["settings_dict"]
        self.assertEqual(settings_dict1, settings_dict4)

    def test_settings_logged_in_user2(self):

        # use the user which has no associated settings_bunch per default

        # login
        login_url = reverse('login_page')
        response = self.client.get(login_url)
        login_form, _ = get_form_by_action_url(response, None)
        login_post_data = generate_post_data_for_form(login_form, spec_values=global_login_data2)
        response = self.client.post(login_url, login_post_data)

        default_settings = SettingsBunch.objects.get(pk=1)
        d = default_settings.get_dict()
        settings_dict1 = self.client.session["settings_dict"]
        self.assertEqual(d, settings_dict1)

        # change the settings
        response = self.client.get(reverse('settings_dialog'))
        form, action_url = get_form_by_action_url(response, "settings_dialog")
        new_settings1 = {"language": "es", "max_rlevel": 13}
        post_data = generate_post_data_for_form(form, spec_values=new_settings1)
        response = self.client.post(action_url, post_data)

        # logout
        self.client.get(reverse('logout_page'))

        # change the settings again
        new_settings2 = {"language": "de", "max_rlevel": 14}
        post_data = generate_post_data_for_form(form, spec_values=new_settings2)
        self.client.post(action_url, post_data)

        # login again and ensure that the values from last login-phase have been saved
        self.client.post(login_url, login_post_data)
        settings_dict2 = self.client.session["settings_dict"]
        self.assertEqual(settings_dict2, new_settings1)

    def test_child_type_lists(self):
        brick = Brick.objects.get(pk=1)

        bt = mh.BrickTree(brick, max_alevel=0)

        # test that the direct children are correctly assigned to direct access lists
        self.assertEqual(len(brick.direct_children_pro), 2)
        self.assertEqual(len(brick.direct_children_contra), 1)
        self.assertEqual(len(brick.direct_children_rest), 3)


class VoteTests(TestCase):
    fixtures = global_fixtures

    # TODO: test proper csrf_token handling (problems with that caused by {%include ... with ... only %})
    # did not show up in the current tests

    def test_voteform(self):
        response = self.client.get(reverse('show_brick', kwargs={"tree_base_brick_id": 2}))

        the_brick = Brick.objects.get(pk=2)
        self.assertEqual(the_brick.cached_avg_vote, 0)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "vote_brick_tree_parent")

        vote_forms = get_all_forms_of_class(response, theclass="nocss_vote_form")

        post_data = generate_post_data_for_form(vote_forms[0], spec_values={"value": 2})

        response = self.client.post(vote_forms[0].action_url, post_data)
        self.assertContains(response, "utc_voting_not_allowed_login")

        self.client.login(**global_login_data1)
        response = self.client.post(vote_forms[0].action_url, post_data)

        the_brick = Brick.objects.get(pk=2)
        self.assertEqual(the_brick.cached_avg_vote, 2.0)

        # change the vote (same user)
        post_data["value"] = -2
        response = self.client.post(vote_forms[0].action_url, post_data)

        the_brick = Brick.objects.get(pk=2)
        self.assertEqual(the_brick.cached_avg_vote, -2.0)

        # vote with different user
        self.client.logout()
        self.client.login(**global_login_data2)

        post_data["value"] = 1
        response = self.client.post(vote_forms[0].action_url, post_data)
        the_brick = Brick.objects.get(pk=2)
        self.assertEqual(the_brick.cached_avg_vote, -0.5)

        # vote with invalid values
        post_data = generate_post_data_for_form(vote_forms[0], spec_values={"value": 3})

        with self.assertRaises(ValueError) as cm:
            response = self.client.post(vote_forms[0].action_url, post_data)

        self.assertTrue("data didn't validate" in cm.exception.args[0])

        # vote for different brick
        post_data = generate_post_data_for_form(vote_forms[1], spec_values={"value": 1})
        the_brick = Brick.objects.get(pk=post_data["vote_brick"])
        self.assertEqual(the_brick.cached_avg_vote, 0)

        response = self.client.post(vote_forms[1].action_url, post_data)
        the_brick = Brick.objects.get(pk=post_data["vote_brick"])
        self.assertEqual(the_brick.cached_avg_vote, 1)

        self.assertTrue("data didn't validate" in cm.exception.args[0])


class ViewTests(TestCase):
    fixtures = global_fixtures

    def test_index(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)

        # search html source for ":()" for variable name
        self.assertNotContains(response, "utc_required_variable:()")

        first_brick = response.context['base'].sorted_child_list[0]
        self.assertEqual(first_brick.title_tag, "Thesis#1")

        # utc = unit test comment
        self.assertNotContains(response, "utc_reaction_brick_drop_down_menu")

        self.assertContains(response, "utc_drop_down_menu_pro")
        self.assertContains(response, "utc_drop_down_menu_contra")
        self.assertContains(response, "utc_drop_down_menu_rest")

        # !! hcl
        self.assertContains(response, "Show Thesis and its Arguments")

        # test whether the group selection works

        self.assertNotContains(response, "utc_nonpublic_thesis")

        self.client.login(**global_login_data1)

        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "utc_nonpublic_thesis")

        first_brick = response.context['base'].sorted_child_list[0]
        self.assertEqual(first_brick.title_tag, "Thesis#9")

    def test_bricktree1(self):

        response = self.client.get(reverse('show_brick', kwargs={"tree_base_brick_id": 1}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "utc_required_variable:()")  # search html source for ":()" for variable name

        self.assertContains(response, "reaction_brick_drop_down_menu")

        brick_list = response.context['base'].sorted_child_list
        b1 = brick_list[0]

        b1_childs = b1.children.all().order_by(*default_brick_ordering)
        b2 = b1_childs[0].children.all().order_by(*default_brick_ordering)[0]

        # test proper sorting of bricks (depth first)
        self.assertEqual(b1.type, Brick.thesis)
        self.assertEqual(b1_childs[0], brick_list[1])
        self.assertEqual(b2, brick_list[2])
        self.assertEqual(b1_childs[1], brick_list[3])

    def test_bricktree2(self):

        response = self.client.get(reverse('show_brick', kwargs={"tree_base_brick_id": 2}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "utc_required_variable:()")  # search html source for ":()" for variable name

        # test to have an url_link to the parent
        link_text = '<a class="url_link" href="/b/{}">'.format(1)
        self.assertContains(response, link_text)

        # test to have an anchor_link to the level_1-child
        link_text = '<a class="anchor_link" href="#{}">'.format(2)
        self.assertContains(response, link_text)

    def test_new_brick_stage1(self):

        response = self.client.get(reverse('new_brick', kwargs={"brick_id": 1, "type_code": "pa"}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "utc_required_variable:()")  # search html source for ":()" for variable name

        # assert that the brick to react on is rendered
        # assert that a new brick is created and rendered after submitting the form
        # assert that the type and ml-classes are correct

    def test_new_brick_stage2(self):

        response1 = self.client.get(reverse('new_brick', kwargs={"brick_id": 1, "type_code": "pa"}))
        self.assertEqual(response1.status_code, 200)

        brick_id = response1.context['brick_id']
        type_code = response1.context['type_code']

        form, action_url = get_form_by_action_url(response1, "new_brick", brick_id=brick_id, type_code=type_code)
        self.assertIsNotNone(form)

        post_data = generate_post_data_for_form(form)

        response2 = self.client.post(action_url, post_data)
        self.assertEqual(response2.status_code, 200)
        self.assertNotContains(response2, "utc_required_variable:()")
        self.assertContains(response2, "utc_form_successfully_processed")

    def test_new_brick_permission(self):
        response1 = self.client.get(reverse('new_brick', kwargs={"brick_id": 9, "type_code": "is"}))

        brick_id = response1.context['brick_id']
        type_code = response1.context['type_code']

        form, action_url = get_form_by_action_url(response1, "new_brick", brick_id=brick_id, type_code=type_code)
        self.assertIsNotNone(form)

        post_data = generate_post_data_for_form(form)

        l1 = len(Brick.objects.all())

        response2 = self.client.post(action_url, post_data)
        l2 = len(Brick.objects.all())

        # assert that the new brick has not been created
        self.assertEqual(l1, l2)

        self.assertEqual(response2.status_code, 403)

    def test_new_thesis_interaction(self):

        response1 = self.client.get(reverse('new_thesis',
                                    kwargs={"brick_id": -1, "type_code": "th"}))
        self.assertEqual(response1.status_code, 200)
        self.assertNotContains(response1, "utc_required_variable:()")  # search html source for ":()" for variable name

        brick_id = response1.context['brick_id']
        type_code = response1.context['type_code']

        form, action_url = get_form_by_action_url(response1, "new_thesis", brick_id=brick_id, type_code=type_code)
        self.assertIsNotNone(form)

        # assert that only 'public' group (with id=1) is visible
        select_nodes = form.findAll("select")
        options = select_nodes[0].find_all("option")
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].attrs["value"], "1")

        logged_in = self.client.login(**global_login_data1)
        response2 = self.client.get(reverse('new_thesis',
                                    kwargs={"brick_id": -1, "type_code": "th"}))

        form2, action_url = get_form_by_action_url(response2, "new_thesis", brick_id=brick_id, type_code=type_code)

        # ensure that all groups are visible
        select_nodes = form2.findAll("select")
        options = select_nodes[0].find_all("option")
        self.assertEqual(len(options), 3)

        post_data = generate_post_data_for_form(form2, spec_values={"title": "new_test_thesis",
                                                                    "associated_group": 2})

        bricks1 = list(Brick.objects.all())

        response3 = self.client.post(action_url, post_data)

        self.assertEqual(response3.status_code, 200)
        self.assertNotContains(response3, "utc_required_variable:()")
        self.assertContains(response3, "utc_form_successfully_processed")

        bricks2 = list(Brick.objects.all())
        new_brick = bricks2[-1]
        self.assertNotIn(new_brick, bricks1)
        self.assertEqual(new_brick.title, "new_test_thesis")
        # assert that a new brick is created and rendered after submitting the form

    def test_edit_brick_stage1(self):

        response = self.client.get(reverse('edit_brick', kwargs={"brick_id": 1}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "utc_required_variable:()")  # search html source for ":()" for variable name

    def test_edit_brick_stage2(self):

        response1 = self.client.get(reverse('edit_brick', kwargs={"brick_id": 2}))
        self.assertEqual(response1.status_code, 200)

        brick_id = response1.context['brick_id']

        form, action_url = get_form_by_action_url(response1, "edit_brick", brick_id=brick_id)
        self.assertIsNotNone(form)

        post_data = generate_post_data_for_form(form)

        response2 = self.client.post(action_url, post_data)

        self.assertEqual(response2.status_code, 200)
        self.assertNotContains(response2, "utc_required_variable:()")

        self.assertContains(response2, "utc_form_successfully_processed")

        # test to have an url_link to the parent
        link_text = '<a class="url_link" href="/b/{}">'.format(1)
        self.assertContains(response2, link_text)

        # test to have no anchor_link to the level_1-child
        link_text = '<a class="anchor_link" href='
        self.assertNotContains(response2, link_text)

        # assert that the the brick-fields have changed
        # assert that the update_time has changed but the creation_time has not

    def test_settings_dialog(self):

        original_data = serializers.serialize("json", SettingsBunch.objects.all())
        response1 = self.client.get(reverse('settings_dialog'))
        self.assertEqual(response1.status_code, 200)
        self.assertContains(response1, "utc_english_language_enabled")

        settings_dict = self.client.session.get("settings_dict")
        self.assertIsNone(settings_dict)

        form, action_url = get_form_by_action_url(response1, "settings_dialog")
        post_data = generate_post_data_for_form(form, spec_values={"language": "de", "max_rlevel": 21})
        response2 = self.client.post(action_url, post_data)
        self.assertContains(response2, "utc_deutsche_sprache_aktiviert")

        settings_dict = self.client.session.get("settings_dict")

        self.assertIsNotNone(settings_dict)
        self.assertEqual(settings_dict["language"], "de")
        self.assertEqual(settings_dict["max_rlevel"], 21)

        new_data = serializers.serialize("json", SettingsBunch.objects.all())

        # database must not have changed
        self.assertEqual(original_data, new_data)

    def test_vote_criterion(self):

        response1 = self.client.get(reverse('thesis_list'))
        self.assertEqual(response1.status_code, 200)
        self.assertContains(response1, "utc_english_language_enabled")

        # test the occurrence of the different vote-criteria
        # if the wording of the vote-criterion changes this has to change as well

        self.assertContains(response1, "Agreement")

        response2 = self.client.get(reverse('show_brick', kwargs={"tree_base_brick_id": 1}))
        self.assertContains(response2, "Agreement")
        self.assertContains(response2, "Cogency")
        self.assertContains(response2, "Relevance")

    def test_debug_view(self):
        response1 = self.client.get(reverse('debug_page'))
        self.assertEqual(response1.status_code, 200)
        self.assertContains(response1, "utc_debug_page")

        # default value is False for unittests
        self.assertFalse(settings.DEBUG)
        self.assertContains(response1, "utc_settings.DEBUG=False")

        settings.DEBUG = True
        response2 = self.client.get(reverse('debug_page'))
        self.assertContains(response2, "utc_settings.DEBUG=True")

        # restore the original value (this is not done automatically)
        settings.DEBUG = False

    def test_debug_view_with_login_required(self):
        """
        Test different ways of logging in and out.
        :return:
        """
        response = self.client.get(reverse('debug_login_page'))
        self.assertEqual(response.status_code, 302)  # redirect to login
        self.assertTrue(response.url.startswith(reverse("login_page")))

        logged_in = self.client.login(**global_login_data1)
        self.assertTrue(logged_in)

        response = self.client.get(reverse('debug_login_page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "utc_debug_page")

        response = self.client.get(reverse('logout_page'))
        self.assertContains(response, "utc_logout_page_logout_success")

        response = self.client.get(reverse('debug_login_page'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login_page")))

        response = self.client.get(reverse('logout_page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "utc_logout_page_not_logged_in")

        # test the login form and page

        action_url = reverse("login_page")
        response = self.client.get(action_url)
        bs = BeautifulSoup(response.content, 'html.parser')
        forms = bs.find_all("form")
        self.assertEqual(len(forms), 1)
        post_data = generate_post_data_for_form(forms[0], spec_values=global_login_data1)

        response = self.client.post(action_url, post_data)
        self.assertEqual(response.url, reverse("profile_page"))
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "utc_profile_page")

        self.client.logout()

    # noinspection PyMethodMayBeStatic
    def test_start_ips(self):
        if 0:
            IPS()
        else:
            print("Omitting debug tool IPS")


# ------------------------------------------------------------------------
# below live some aliases to quickly access specific tests
# ------------------------------------------------------------------------

# run shortcut: py3 manage.py test sober.tests.T.ips

T = ViewTests
T.a = T.test_settings_dialog
T.ips = T.test_start_ips

# python manage.py test sober.tests.T.ips

# ------------------------------------------------------------------------
# below lives auxiliary code which is related to testing but does not contain tests
# ------------------------------------------------------------------------


def get_form_by_action_url(response, url_name, **url_name_kwargs):
    """
    Auxiliary function that returns a bs-object of the form which is specifies by action-url.

    Also return action_url

    :param response:
    :param url_name:
    :param url_name_kwargs:
    :return:
    """
    bs = BeautifulSoup(response.content, 'html.parser')
    forms = bs.find_all("form")
    if url_name is None:
        # this accounts for the case where no action is specified (by some generic views)
        action_url = None
    else:
        action_url = reverse(url_name, kwargs=url_name_kwargs)

    for form in forms:
        action = form.attrs.get("action")
        if action == action_url:
            return form, action_url

    return None, action_url


def get_all_forms_of_class(response, theclass):
    """
    Return a list of form-objects which belong to the given class.

    This is the usecase for 'nocss_...'-classes.

    Note, this function also creates an attribute .action_url

    :param response:
    :param theclass:
    :return:
    """

    bs = BeautifulSoup(response.content, 'html.parser')
    forms = bs.find_all("form")

    res = []
    for form in forms:
        classes = form.attrs.get("class")
        if theclass in classes:
            res.append(form)

        form.action_url = form.attrs.get("action")
    return res


def get_form_fields_to_submit(form):
    """
    Return two lists: fields and hidden_fields.

    :param form:
    :return:
    """

    inputs = form.find_all("input")
    textareas = form.find_all("textarea")

    post_fields = inputs + textareas

    types_to_omit = ["submit", "cancel"]

    fields = []
    hidden_fields = []
    for field in post_fields:
        ftype = field.attrs.get("type")
        if ftype in types_to_omit:
            continue

        if ftype == "hidden":
            hidden_fields.append(field)
        else:
            fields.append(field)

    return fields, hidden_fields


def generate_post_data_for_form(form, default_value="xyz", spec_values=None):
    """
    Return a dict containing all dummy-data for the form

    :param form:
    :param default_value:   str; use this value for all not specified fields
    :param spec_values:     dict; use these values to override default value

    :return:                dict of post_data
    """

    if spec_values is None:
        spec_values = {}

    fields, hidden_fields = get_form_fields_to_submit(form)

    post_data = {}
    for f in hidden_fields:
        post_data[f.attrs['name']] = f.attrs['value']

    for f in fields:
        post_data[f.attrs['name']] = default_value

    post_data.update(spec_values)

    return post_data




