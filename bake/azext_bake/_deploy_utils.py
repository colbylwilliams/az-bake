# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import json
from time import sleep

from azure.cli.core.commands import LongRunningOperation, upsert_to_collection
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.profiles import ResourceType, get_sdk
from azure.cli.core.util import find_child_item, random_string, sdk_no_wait
from knack.log import get_logger
from knack.util import CLIError
from msrestazure.tools import parse_resource_id, resource_id

from ._client_factory import cf_network, cf_resources

TRIES = 3

logger = get_logger(__name__)

# pylint: disable=inconsistent-return-statements


def is_bicep_file(file_path):
    return file_path.lower().endswith(".bicep")


def deploy_arm_template_at_resource_group(cmd, resource_group_name=None, template_file=None,
                                          template_uri=None, parameters=None, no_wait=False):

    from azure.cli.command_modules.resource.custom import (
        JsonCTemplatePolicy, _prepare_deployment_properties_unmodified)

    properties = _prepare_deployment_properties_unmodified(cmd, 'resourceGroup', template_file=template_file,
                                                           template_uri=template_uri, parameters=parameters,
                                                           mode='Incremental')
    smc = cf_resources(cmd.cli_ctx)
    client = smc.deployments

    if template_file:
        # Plug this as default HTTP pipeline
        from azure.core.pipeline import Pipeline
        smc._client._pipeline._impl_policies.append(JsonCTemplatePolicy())
        # Because JsonCTemplatePolicy needs to be wrapped as _SansIOHTTPPolicyRunner, so a new Pipeline is built
        smc._client._pipeline = Pipeline(
            policies=smc._client._pipeline._impl_policies,
            transport=smc._client._pipeline._transport
        )

    for try_number in range(TRIES):
        try:
            deployment_name = random_string(length=14, force_lower=True) + str(try_number)

            Deployment = cmd.get_models('Deployment', resource_type=ResourceType.MGMT_RESOURCE_RESOURCES)
            deployment = Deployment(properties=properties)

            deploy_poll = sdk_no_wait(no_wait, client.begin_create_or_update, resource_group_name,
                                      deployment_name, deployment)

            result = LongRunningOperation(cmd.cli_ctx, start_msg='Deploying ARM template',
                                          finish_msg='Finished deploying ARM template')(deploy_poll)

            props = getattr(result, 'properties', None)
            return result, getattr(props, 'outputs', None)
        except CLIError as err:
            if try_number == TRIES - 1:
                raise err
            try:
                response = getattr(err, 'response', None)
                message = json.loads(response.text)['error']['details'][0]['message']
                if '(ServiceUnavailable)' not in message:
                    raise err
            except:
                raise err from err
            sleep(5)
            continue


def get_arm_output(outputs, key, raise_on_error=True):
    try:
        value = outputs[key]['value']
    except KeyError as e:
        if raise_on_error:
            raise CLIError(
                f"A value for '{key}' was not provided in the ARM template outputs") from e
        value = None

    return value


def create_subnet(cmd, vnet, subnet_name, address_prefix):
    Subnet = cmd.get_models('Subnet', resource_type=ResourceType.MGMT_NETWORK)

    vnet_parts = parse_resource_id(vnet)

    vnet_name = vnet_parts['name']
    resource_group_name = vnet_parts['resource_group']

    subnet = Subnet(name=subnet_name, address_prefix=address_prefix)
    subnet.private_endpoint_network_policies = "Disabled"
    subnet.private_link_service_network_policies = "Enabled"

    client = cf_network(cmd.cli_ctx).subnets

    create_poller = client.begin_create_or_update(resource_group_name, vnet_name, subnet_name, subnet)

    result = LongRunningOperation(cmd.cli_ctx, start_msg=f'Creating {subnet_name}',
                                  finish_msg=f'Finished creating {subnet_name}')(create_poller)

    logger.warning(result)

    return result


def tag_resource_group(cmd, resource_group_name, tags):
    Tags, TagsPatchResource = cmd.get_models(
        'Tags', 'TagsPatchResource', resource_type=ResourceType.MGMT_RESOURCE_RESOURCES)

    sub = get_subscription_id(cmd.cli_ctx)
    scope = resource_id(subscription=sub, resource_group=resource_group_name)

    properties = Tags(tags=tags)
    paramaters = TagsPatchResource(operation='Merge', properties=properties)

    client = cf_resources(cmd.cli_ctx).tags
    result = client.update_at_scope(scope, paramaters)
    return result


def get_resource_group_tags(cmd, resource_group_name):
    sub = get_subscription_id(cmd.cli_ctx)
    scope = resource_id(subscription=sub, resource_group=resource_group_name)
    client = cf_resources(cmd.cli_ctx).tags
    result = client.get_at_scope(scope)
    return result.properties.tags


# def get_gallery():
