#!/usr/bin/env python

import requests

class PostMixin():
    def post_json(self, endpoint, message=None):
        response = requests.post(
            endpoint,
            json=message,
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code != 200:
            raise ValueError(
                'Request to %s returned an error %s, the response is:\n%s'
                % (endpoint, response.status_code, response.text)
            )
        return response