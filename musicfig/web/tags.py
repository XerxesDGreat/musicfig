import logging

from . import web
from ..nfc_tag import NFCTagStore
from flask import \
    current_app, \
    redirect, \
    render_template, \
    request, \
    session, \
    url_for

logger = logging.getLogger(__name__)

@web.route("/tags", methods=["GET"])
def tag_list():
    logger.info("listing tags")
    return render_template("tags.html", nfc_tags=NFCTagStore.get_all_nfc_tags())

@web.route("/tags/create", methods=["GET"])
def tag_create_form():
    new_tag_id = request.args.get("tag_id")
    return render_template("create_tag.html", tag_id=new_tag_id)

@web.route("/tags/create", methods=["POST"])
def create_tag():
    tag_id = request.form.get("id")
    name = request.form.get("name")
    description = request.form.get("description")
    tag_type = request.form.get("tagType")
    attributes = request.form.get("tagAttributes")
    logger.info("%s, %s, %s, %s, %s", tag_id, name, description, tag_type, attributes)
    return redirect(url_for("web.tag_list"))