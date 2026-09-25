"""Run the Streamlit server with its one internet lookup switched off.

When shared on a network, Streamlit asks checkip.amazonaws.com for this
computer's public address. Render QA never needs it, and client work must not
touch outside services, so the lookup is replaced before the server starts.
Takes the same arguments as ``streamlit``, e.g. ``python serve.py run app.py``.
"""

import sys

import streamlit.net_util as net_util

net_util.get_external_ip = lambda: None

from streamlit.web import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main())
