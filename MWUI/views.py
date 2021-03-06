#!/usr/bin/env python3.4
# -*- coding: utf-8 -*-
#
#  Copyright 2016 Ramil Nugmanov <stsouko@live.ru>
#  This file is part of predictor.
#
#  predictor 
#  is free software; you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
import uuid
from .forms import (Login, Registration, ReLogin, ChangePassword, NewPost, ChangeRole, BanUser, ForgotPassword,
                    Meeting, Profile, DeleteButton)
from .redirect import get_redirect_target
from .logins import User
from .models import Users, Blog
from .config import UserRole, BLOG_POSTS, Glyph, UPLOAD_PATH, IMAGES_ROOT, BlogPost, LAB_NAME, MeetingPost
from .bootstrap import Pagination
from .sendmail import send_mail
from .scopus import get_articles
from flask import redirect, url_for, render_template, Blueprint, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from pony.orm import db_session, select, commit
from datetime import datetime
from os import path


conf_pages = (BlogPost.THESIS, BlogPost.SERVICE, BlogPost.MEETING)
view_bp = Blueprint('view', __name__)


def save_upload(field, images=False):
    file_name = '%s%s' % (uuid.uuid4(), path.splitext(field.data.filename)[-1])
    field.data.save(path.join(IMAGES_ROOT if images else UPLOAD_PATH, file_name))
    return file_name


def blog_viewer(page, selector):
    if page < 1:
        return None
    with db_session:
        q = select(x for x in Blog).filter(selector)
        count = q.count()
        pag = Pagination(page, count, pagesize=BLOG_POSTS)
        if page != pag.page:
            return None

        data = []
        for p in q.order_by(Blog.date.desc()).page(page, pagesize=BLOG_POSTS):
            tmp = dict(date=p.date.strftime('%B %d, %Y'), glyph=Glyph[p.type.name].value, title=p.title,
                       body=p.body, url=url_for('.blog_post', post=p.id), author=p.author.name, banner=p.banner)
            data.append(tmp)

    return data, pag


@view_bp.errorhandler(404)
def page_not_found(*args, **kwargs):
    return render_template('layout.html', title='404', subtitle='Page not found'), 404


@view_bp.route('/registration', methods=['GET', 'POST'])
def registration():
    if current_user.is_authenticated:
        return redirect(get_redirect_target() or url_for('.index'))

    registration_form = Registration(prefix='Registration')
    forms = [('Not Registered?', registration_form)]

    if registration_form.validate_on_submit():
        with db_session:
            m = select(x for x in Blog if x.post_type == BlogPost.EMAIL.value and x.special['type'] == 'reg').first()
            u = Users(email=registration_form.email.data, password=registration_form.password.data,
                      name=registration_form.name.data, job=registration_form.job.data,
                      town=registration_form.town.data, country=registration_form.country.data,
                      status=registration_form.status.data)

            send_mail((m and m.body or 'Welcome! %s.') % u.name, u.email, to_name=u.name,
                      subject=m and m.title or 'Welcome', banner=m and m.banner or None, title=m and m.title or None)

        login_user(User(u), remember=False)
        return registration_form.redirect()

    return render_template('forms.html', forms=forms, title='Registration')


@view_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(get_redirect_target() or url_for('.index'))

    login_form = Login(prefix='Login')
    forgot_form = ForgotPassword(prefix='ForgotPassword')

    forms = [('Welcome Back!', login_form), ('Forgot Password?', forgot_form)]

    if login_form.validate_on_submit():
        user = User.get(login_form.email.data, login_form.password.data)
        if user:
            login_user(user, remember=login_form.remember.data)
            return login_form.redirect()
        flash('Invalid Credentials', 'warning')

    elif forgot_form.validate_on_submit():
        with db_session:
            u = Users.get(email=forgot_form.email.data)
            if u:
                m = select(x for x in Blog if x.post_type == BlogPost.EMAIL.value and
                           x.special['type'] == 'rep').first()
                u.gen_restore()
                send_mail((m and m.body or '%s\n\nYour restore password: %s') % (u.name, u.restore), u.email,
                          to_name=u.name, subject=m and m.title or 'Forgot password?',
                          banner=m and m.banner or None, title=m and m.title or None)
        flash('Check your email box', 'warning')
        return redirect(url_for('.login'))

    return render_template('forms.html', forms=forms, title='Login')


@view_bp.route('/logout', methods=['GET'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('.login'))


@view_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    with db_session:
        admin = current_user.role_is(UserRole.ADMIN)
        user_form = Profile(prefix='EditProfile', obj=current_user.get_user())
        re_login_form = ReLogin(prefix='ReLogin')
        change_passwd_form = ChangePassword(prefix='ChangePassword')

        forms = [('Edit Profile', user_form), ('Log out on all devices', re_login_form),
                 ('Change Password', change_passwd_form)]

        if admin:
            new_post_form = NewPost(prefix='NewPost')
            change_role_form = ChangeRole(prefix='ChangeRole')
            ban_form = BanUser(prefix='BanUser')

            forms.extend([('New Blog Post', new_post_form), ('Change User Role', change_role_form),
                          ('Ban User', ban_form)])

        """ forms parsing
        """
        if user_form.validate_on_submit():
            u = Users.get(id=current_user.id)
            u.name = user_form.name.data
            u.country = user_form.country.data
            if user_form.job.data:
                u.job = user_form.job.data
            if user_form.town.data:
                u.town = user_form.town.data
            if user_form.status.data:
                u.status = user_form.status.data
            flash('Profile updated')
        elif re_login_form.validate_on_submit():
            u = Users.get(id=current_user.id)
            u.change_token()
            logout_user()
            flash('Successfully logged out from all devices')
            return redirect(url_for('.login'))
        elif change_passwd_form.validate_on_submit():
            u = Users.get(id=current_user.id)
            u.change_password(change_passwd_form.password.data)
            logout_user()
            flash('Successfully changed password')
            return redirect(url_for('.login'))

        elif admin:
            if new_post_form.validate_on_submit():
                def add_post(parent=None):
                    banner_name = save_upload(new_post_form.banner, images=True) if new_post_form.banner.data else None
                    file_name = save_upload(new_post_form.attachment) if new_post_form.attachment.data else None
                    p = Blog(type=new_post_form.type, title=new_post_form.title.data, slug=new_post_form.slug.data,
                             body=new_post_form.body.data, banner=banner_name, special=new_post_form.special,
                             attachment=file_name, author=Users.get(id=current_user.id), parent=parent)
                    commit()
                    return redirect(url_for('.blog_post', post=p.id))

                if new_post_form.type == BlogPost.SERVICE:
                    if new_post_form.parent_field.data:
                        r = Blog.get(id=new_post_form.parent_field.data)
                        if r and r.type == BlogPost.MEETING:
                            return add_post(r)
                    new_post_form.parent_field.errors = ['Need parent']
                else:
                    return add_post()

            elif change_role_form.validate_on_submit():
                u = Users.get(email=change_role_form.email.data)
                u.user_role = change_role_form.type.value
                flash('Successfully changed %s (%s) role' % (u.name, u.email))
            elif ban_form.validate_on_submit():
                pass

    return render_template("forms.html", title='Profile', subtitle=current_user.name, forms=forms)


@view_bp.route('/', methods=['GET'])
@view_bp.route('/index', methods=['GET'])
def index():
    with db_session:
        c = select(x for x in Blog if x.post_type == BlogPost.CAROUSEL.value
                   and x.banner is not None).order_by(Blog.id.desc()).limit(BLOG_POSTS)
        carousel = [dict(banner=x.banner, url=url_for('.blog_post', post=x.id), title=x.title, body=x.body) for x in c]

        ip = select(x for x in Blog if x.post_type == BlogPost.IMPORTANT.value)
        info = [dict(url=url_for('.blog_post', post=x.id), title=x.title, body=x.body)
                for x in ip.order_by(Blog.id.desc()).limit(3)]

        pl = select(x for x in Blog if x.post_type == BlogPost.PROJECTS.value)

        projects = []
        for x in pl.order_by(Blog.date.desc()):
            projects.append(dict(url=url_for('.blog_post', post=x.id), body=x.body, title=x.title, banner=x.banner))

    return render_template("home.html", carousel=carousel, projects=dict(list=projects, title='Our Projects'),
                           info=info, title='Welcome to', subtitle=LAB_NAME)


@view_bp.route('/about', methods=['GET'])
def about():
    with db_session:
        a = select(x for x in Blog if x.post_type == BlogPost.ABOUT.value).first()
        if a:
            about_us = dict(body=a.body, title=a.title, url=url_for('.blog_post', post=a.id), banner=a.banner)
        else:
            about_us = None

        p = select(x for x in Blog if x.post_type == BlogPost.CHIEF.value)
        chief = []
        for x in p:
            chief.append(dict(title=x.title, url=url_for('.blog_post', post=x.id), body=x.body, banner=x.banner,
                              role=x.special and x.special.get('role', 'Researcher') or 'Researcher',
                              order=x.special and x.special.get('order', 0) or 0))

        p = select(x for x in Blog if x.post_type == BlogPost.TEAM.value).order_by(Blog.id.desc())
        team = []
        for x in p:
            team.append(dict(title=x.title, url=url_for('.blog_post', post=x.id), body=x.body, banner=x.banner))

    return render_template("about.html", title='About', subtitle='Laboratory', about=about_us,
                           data=dict(chief=sorted(chief, key=lambda x: x['order'], reverse=True),
                                     team=team, title='Our Team'))


@view_bp.route('/blog/post/<int:post>', methods=['GET', 'POST'])
def blog_post(post):
    admin = current_user.is_authenticated and current_user.role_is(UserRole.ADMIN)
    edit_post_form = None
    remove_post_form = None
    special_form = None
    special_field = None
    children = []
    title = None

    with db_session:
        p = Blog.get(id=post)
        if not p:
            return redirect(url_for('.blog'))

        """ collect sidebar
        """
        ip = select(x for x in Blog if x.post_type == BlogPost.IMPORTANT.value and x.id != post)
        info = [dict(url=url_for('.blog_post', post=x.id), title=x.title, body=x.body)
                for x in ip.order_by(Blog.date.desc()).limit(3)]

        """ admin page
        """
        if admin:
            remove_post_form = DeleteButton(prefix='Delete')
            edit_post_form = NewPost(prefix='Edit', obj=p)
            if remove_post_form.validate_on_submit():
                p.delete()
                remove_post_form.redirect('.blog')
                return redirect(url_for('.blog'))
            elif edit_post_form.validate_on_submit():
                p.body = edit_post_form.body.data
                p.title = edit_post_form.title.data
                p.date = datetime.utcnow()

                if p.type not in conf_pages and edit_post_form.type not in conf_pages:
                    p.post_type = edit_post_form.type.value
                if edit_post_form.parent_field.data and p.type == BlogPost.SERVICE:
                    parent = edit_post_form.parent_field.data != post and Blog.get(id=edit_post_form.parent_field.data)
                    if parent:
                        p.parent = parent
                if edit_post_form.slug.data:
                    p.slug = edit_post_form.slug.data
                if edit_post_form.special:
                    p.special = edit_post_form.special
                if edit_post_form.banner.data:
                    p.banner = save_upload(edit_post_form.banner, images=True)
                if edit_post_form.attachment.data:
                    p.attachment = save_upload(edit_post_form.attachment)

        """ sidebar for nested posts
        """
        _parent = p.parent or p
        for i in _parent.children or []:  # need order
            if i.post_type == BlogPost.SERVICE.value and i.id != post:
                children.append(dict(title=i.title, url=url_for('.blog_post', post=i.id),
                                     order=i.special and i.special.get('order', 0) or 0))

        if _parent.type == BlogPost.MEETING:
            children.append(dict(title='Participants', url=url_for('.participants', event=_parent.id), order=20))

        """ SERVICE POST
        """
        if p.type == BlogPost.SERVICE:
            crumb = dict(url=url_for('.blog_post', post=p.parent.id), title=p.title, parent='Event')
            title = p.parent.title
            _type = p.special and p.special.get('type')
            if _type == 'reg':
                if datetime.fromtimestamp(p.parent.special.get('deadline', 0)) > datetime.utcnow():
                    if current_user.is_authenticated and not select(x for x in Blog
                                                                    if x.author.id == current_user.id
                                                                    and x.post_type == BlogPost.THESIS.value
                                                                    and x.parent.id == post).exists():
                        special_form = Meeting(prefix='Meeting')
                        if special_form.validate_on_submit():
                            banner_name = save_upload(special_form.banner,
                                                      images=True) if special_form.banner.data else None
                            file_name = save_upload(special_form.attachment) if special_form.attachment.data else None
                            w = Blog(type=BlogPost.THESIS, title=special_form.title.data, body=special_form.body.data,
                                     banner=banner_name, special=special_form.special, attachment=file_name,
                                     author=Users.get(id=current_user.id), parent=p.parent)
                            commit()
                            return redirect(url_for('.blog_post', post=w.id))

        elif p.type == BlogPost.THESIS:
            if current_user.is_authenticated and p.author.id == current_user.id and \
                    datetime.fromtimestamp(p.parent.special.get('deadline', 0)) > datetime.utcnow():
                p.participation = p.special.get('participation')
                special_form = Meeting(prefix='Meeting', obj=p)
                if special_form.validate_on_submit():
                    p.title = special_form.title.data
                    p.body = special_form.body.data
                    p.special.update(special_form.special)

                    if special_form.banner.data:
                        p.banner = save_upload(special_form.banner, images=True)
                    if special_form.attachment.data:
                        p.attachment = save_upload(special_form.attachment)

            crumb = dict(url=url_for('.blog_post', post=p.parent.id), title='Abstract', parent='Event')
            special_field = '**Presentation Type**: *%s*' % MeetingPost(p.special.get('participation')).name
        elif p.type in (BlogPost.CHIEF, BlogPost.TEAM):
            crumb = dict(url=url_for('.about'), title='Member', parent='Laboratory')
            scopus = p.special.get('scopus')
            if scopus:
                special_field = get_articles(scopus)

        elif p.type == BlogPost.ABOUT:
            crumb = dict(url=url_for('.about'), title='Description', parent='Laboratory')
        else:
            crumb = dict(url=url_for('.blog'), title='Post', parent='News')

        """ final data preparation
        """
        data = dict(date=p.date.strftime('%B %d, %Y at %H:%M'), title=p.title, body=p.body, author=p.author.name,
                    banner=p.banner)
        if p.attachment:
            data['attachment'] = url_for('static', filename='docs/%s' % p.attachment)

    return render_template("post.html", title=title or p.title, post=data, info=info,
                           children=sorted(children, key=lambda x: x['order']),
                           edit_form=edit_post_form, remove_form=remove_post_form, crumb=crumb,
                           special_form=special_form, special_field=special_field)


@view_bp.route('/search', methods=['GET'])
@login_required
def search():
    return render_template("layout.html")


@view_bp.route('/queries', methods=['GET'])
@login_required
def queries():
    return render_template("layout.html")


@view_bp.route('/results', methods=['GET'])
@login_required
def results():
    return render_template("layout.html")


@view_bp.route('/predictor', methods=['GET'])
@login_required
def predictor():
    return render_template("predictor.html")


@view_bp.route('/blog/', methods=['GET'])
@view_bp.route('/blog/<int:page>', methods=['GET'])
def blog(page=1):
    res = blog_viewer(page, lambda x: x.post_type not in (BlogPost.THESIS.value, BlogPost.EMAIL.value,
                                                          BlogPost.SERVICE.value))
    if not res:
        return redirect(url_for('.blog'))

    return render_template("blog.html", paginator=res[1], posts=res[0], title='News', subtitle='chart')


@view_bp.route('/events', methods=['GET'])
@view_bp.route('/events/<int:page>', methods=['GET'])
@login_required
def events(page=1):
    res = blog_viewer(page, lambda x: x.post_type == BlogPost.THESIS.value and x.author.id == current_user.id)
    if not res:
        return redirect(url_for('.events'))

    return render_template("blog.html", paginator=res[1], posts=res[0], title='Events', subtitle='Presentations')


@view_bp.route('/participants/<int:event>', methods=['GET'])
@view_bp.route('/participants/<int:event>/<int:page>', methods=['GET'])
@login_required
def participants(event, page=1):
    with db_session:
        b = Blog.get(id=event, post_type=BlogPost.MEETING.value)
    if not b:
        return redirect(url_for('.blog'))

    res = blog_viewer(page, lambda x: x.post_type == BlogPost.THESIS.value and x.parent.id == event)
    if not res:
        return redirect(url_for('.participants', event=event))

    return render_template("blog.html", paginator=res[1], posts=res[0], title=b.title, subtitle='Participants',
                           crumb=dict(url=url_for('.blog_post', post=event), title='Presentations', parent='Event'))


@view_bp.route('/emails', methods=['GET'])
@view_bp.route('/emails/<int:page>', methods=['GET'])
@login_required
def emails(page=1):
    if not current_user.role_is(UserRole.ADMIN):
        return redirect(url_for('.index'))

    res = blog_viewer(page, lambda x: x.post_type == BlogPost.EMAIL.value)
    if not res:
        return redirect(url_for('.emails'))

    return render_template("blog.html", paginator=res[1], posts=res[0], title='E-mail templates', subtitle='list')


@view_bp.route('/<string:slug>/')
def slug(slug):
    with db_session:
        p = Blog.get(slug=slug)
        if not p:
            abort(404)
    return redirect(url_for('.blog_post', post=p.id))
