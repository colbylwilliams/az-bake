# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from azure.cli.core.commands.client_factory import get_mgmt_service_client
from azure.cli.core.profiles import ResourceType


def resource_client_factory(cli_ctx, subscription_id=None, **_):
    return get_mgmt_service_client(cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES,
                                   subscription_id=subscription_id)


def auth_client_factory(cli_ctx, scope=None):
    import re
    subscription_id = None
    if scope:
        matched = re.match('/subscriptions/(?P<subscription>[^/]*)/', scope)
        if matched:
            subscription_id = matched.groupdict()['subscription']
    return get_mgmt_service_client(cli_ctx, ResourceType.MGMT_AUTHORIZATION, subscription_id=subscription_id)


# def _graph_client_factory(cli_ctx, **_):
#     from ._msgrpah import GraphClient
#     client = GraphClient(cli_ctx)
#     return client

def get_graph_client(cli_ctx):
    from azure.cli.command_modules.role import graph_client_factory
    return graph_client_factory(cli_ctx)
