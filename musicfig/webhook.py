import requests

class PostMixin():
    def post_json(self, endpoint, message=""):
        """
        Posts the given json message to the given endpoint

        Positional arguments:
        endpoint -- string endpoint to call
        message -- any json content to send with the request. Note that this should
                   be an empty string if no content is being sent; as such, any None
                   values will be converted to an empty string. This is so the call,
                   like, _succeeds_ and such
        
        returns the response object

        raises ValueError if the response code comes back as non-200 (which is... not
        _ideal_, but I haven't tuned it yet; we'll get to that)
        """
        message = "" if message is None else message
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