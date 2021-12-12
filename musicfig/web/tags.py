import json
from json.decoder import JSONDecodeError
import logging

from . import web
from ..nfc_tag import NFCTagStore, NFCTagManager
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
    created_tag_id = session.get("created_tag_id")
    return render_template("tags.html", nfc_tags=NFCTagStore.get_all_nfc_tags(), created_tag_id=created_tag_id)

# maybe creating a new one could just be visually represented as adding a new row to the table

@web.route("/tags/create", methods=["GET"])
def tag_create_form():
    new_tag_id = request.args.get("tag_id")
    return render_template("create_tag.html", tag_id=new_tag_id)

@web.route("/tags/create", methods=["POST"])
def create_tag():
    # upon creation, make sure we have the requisite attributes; otherwise will crash later
    logger.info(request.form)
    # might be better to do an API endpoint
    tag_id = request.form.get("tag_id")
    if tag_id is None:
        logger.error("id was blank")
        return redirect(url_for("web.tag_create_form"))
    name = request.form.get("name")
    description = request.form.get("description")
    tag_type = request.form.get("tag_type")
    if tag_type is None:
        logger.error("tag_type was blank")
        return redirect(url_for("web.tag_create_form"))
    attributes = request.form.get("tag_attributes")
    if attributes is not None:
        try:
            json.loads(attributes)
        except JSONDecodeError as e:
            logger.exception("must be a json string")
            return redirect(url_for("web.tag_create_form"))
    logger.info("%s, %s, %s, %s, %s", tag_id, name, description, tag_type, attributes)

    NFCTagManager.get_instance().create_nfc_tag(tag_id, tag_type, name=name, description=description, attributes=attributes)
    session["created_tag_id"] = tag_id
    return redirect(url_for("web.tag_list"))