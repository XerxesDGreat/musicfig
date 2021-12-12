import logging

from . import web
from ..nfc_tag import NFCTagStore
from flask import \
    current_app, \
    redirect, \
    render_template, \
    request, \
    session

logger = logging.getLogger(__name__)

@web.route("/tags", methods=["GET"])
def tag_list():
    logger.info("listing tags")
    return render_template("tags.html", nfc_tags=NFCTagStore.get_all_nfc_tags())

@web.route("/tags/create", methods=["GET"])
def tag_create():
    new_tag_id = request.args.get("tag_id")
    return render_template("create_tag.html", tag_id=new_tag_id)