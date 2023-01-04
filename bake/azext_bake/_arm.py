# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=logging-fstring-interpolation, protected-access, inconsistent-return-statements, raise-missing-from

import json

from time import sleep

from azure.cli.command_modules.role.custom import create_role_assignment
from azure.cli.core.commands import LongRunningOperation
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.profiles import ResourceType, get_sdk
from azure.cli.core.util import random_string, sdk_no_wait
from azure.core.exceptions import ResourceNotFoundError
from knack.util import CLIError
from msrestazure.tools import parse_resource_id, resource_id

from ._client_factory import cf_compute, cf_msi, cf_network, cf_resources
from ._utils import get_logger

TRIES = 3

logger = get_logger(__name__)


# ----------------
# ARM Deployments
# ----------------


def is_bicep_file(file_path):
    return file_path.lower().endswith(".bicep")


def deploy_arm_template_at_resource_group(cmd, resource_group_name=None, template_file=None,
                                          template_uri=None, parameters=None, no_wait=False):

    from azure.cli.command_modules.resource.custom import JsonCTemplatePolicy, _prepare_deployment_properties_unmodified

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
    if not outputs:
        return None
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


def get_resource_group_by_name(cli_ctx, resource_group_name):
    subscription_id = get_subscription_id(cli_ctx)
    try:
        resource_client = cf_resources(cli_ctx).resource_groups
        return resource_client.get(resource_group_name), subscription_id
    except Exception as ex:  # pylint: disable=broad-except
        error = getattr(ex, 'Azure Error', ex)
        if error != 'ResourceGroupNotFound':
            return None, subscription_id
        raise


def create_resource_group(cli_ctx, resource_group_name, location, tags=None):
    subscription_id = get_subscription_id(cli_ctx)
    ResourceGroup = get_sdk(cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES, 'ResourceGroup', mod='models')
    resource_client = cf_resources(cli_ctx).resource_groups
    parameters = ResourceGroup(location=location.lower(), tags=tags)
    return resource_client.create_or_update(resource_group_name, parameters), subscription_id


# ----------------
# Compute Gallery
# ----------------


def ensure_gallery_permissions(cmd, gallery_id: str, identity_id: str, create_assignment=True):
    from azure.cli.command_modules.role.custom import list_role_assignments

    i_parts = parse_resource_id(identity_id)
    i_name, i_rg = i_parts['name'], i_parts['resource_group']

    g_parts = parse_resource_id(gallery_id)
    g_sub, g_rg = g_parts['subscription'], g_parts['resource_group']
    g_rgid = resource_id(subscription=g_sub, resource_group=g_rg)

    identity_client = cf_msi(cmd.cli_ctx).user_assigned_identities
    identity = identity_client.get(i_rg, i_name)

    assignments = list_role_assignments(cmd, assignee=identity.principal_id, scope=g_rgid)

    if not assignments or not any(a for a in assignments if a['roleDefinitionName'] in ['Contributor', 'Owner']):
        logger.warning(f'Identity {i_name} does not have permissions to access the Gallery Resource Group {g_rg}.')
        if not create_assignment:
            logger.warning('Please ensure the identity has Contributor or Owner permissions '
                           'on the Gallery Resource Group.')
        else:
            logger.warning(f'Granting {i_name} Contributor permissions on {g_rg}...')
            try:
                create_role_assignment(cmd, role='Contributor', assignee_object_id=identity.principal_id,
                                       scope=g_rgid, assignee_principal_type='ServicePrincipal')
            except:
                raise CLIError('Failed to grant permissions to the identity. Please ensure the identity has '
                               'Contributor or Owner permissions on the Gallery Resource Group.')

    return identity.principal_id


# def ensure_sandbox_permissions(cmd, sandbox_id, identity_id):
#     logger('Ensuring permissions for sandbox %s', sandbox_id)

def get_gallery(cmd, resource_group_name: str, gallery_name: str):
    logger.info(f'Getting gallery {gallery_name} in resource group {resource_group_name}')
    client = cf_compute(cmd.cli_ctx)
    try:
        gallery = client.galleries.get(resource_group_name, gallery_name)
        return gallery
    except ResourceNotFoundError:
        logger.info(f'Gallery {gallery_name} not found in resource group {resource_group_name}')
        return None


def get_image_definition(cmd, resource_group_name: str, gallery_name: str, gallery_image_name: str):
    logger.info(f'Getting image definition {gallery_image_name} from gallery {gallery_name}')
    client = cf_compute(cmd.cli_ctx)
    try:
        definition = client.gallery_images.get(resource_group_name, gallery_name, gallery_image_name)
        return definition
    except ResourceNotFoundError:
        logger.info(f'Image definition {gallery_image_name} not found in {gallery_name}')
        return None


def get_image_version(cmd, resource_group_name: str, gallery_name: str, gallery_image_name: str, gallery_image_version_name: str):
    logger.info(f'Getting version {gallery_image_version_name} of {gallery_image_name} in gallery {gallery_name}')
    client = cf_compute(cmd.cli_ctx)
    try:
        version = client.gallery_image_versions.get(resource_group_name, gallery_name,
                                                    gallery_image_name, gallery_image_version_name)
        return version
    except ResourceNotFoundError:
        logger.info(f'Version {gallery_image_version_name} of {gallery_image_name} not found.')
        return None


def image_version_exists(cmd, resource_group_name: str, gallery_name: str, gallery_image_name: str, gallery_image_version_name: str):
    version = get_image_version(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name)
    return version is not None

# pylint: disable=unused-argument, unused-variable


def create_image_definition(cmd, resource_group_name, gallery_name, gallery_image_name, publisher, offer, sku,
                            location=None, os_type='Windows', os_state='Generalized', end_of_life_date=None,
                            description=None, tags=None):
    logger.info(f'Creating image definition {gallery_image_name} in gallery {gallery_name} ...')

    if location is None:
        location = get_gallery(cmd, resource_group_name, gallery_name).location

    client = cf_compute(cmd.cli_ctx)
    # GalleryImage, GalleryImageIdentifier, RecommendedMachineConfiguration, ResourceRange, Disallowed, \
    # ImagePurchasePlan, GalleryImageFeature = cmd.get_models(
    #     'GalleryImage', 'GalleryImageIdentifier', 'RecommendedMachineConfiguration', 'ResourceRange',
    #     'Disallowed', 'ImagePurchasePlan', 'GalleryImageFeature',
    #     resource_type=ResourceType.MGMT_COMPUTE, operation_group='galleries')
    GalleryImage, GalleryImageIdentifier, Disallowed, GalleryImageFeature = cmd.get_models(
        'GalleryImage', 'GalleryImageIdentifier', 'Disallowed', 'GalleryImageFeature',
        resource_type=ResourceType.MGMT_COMPUTE, operation_group='galleries')

    purchase_plan = None
    # if any([plan_name, plan_publisher, plan_product]):
    #     purchase_plan = ImagePurchasePlan(name=plan_name, publisher=plan_publisher, product=plan_product)
    feature_list = [
        GalleryImageFeature(name='SecurityType', value='TrustedLaunch')
    ]

    image = GalleryImage(identifier=GalleryImageIdentifier(publisher=publisher, offer=offer, sku=sku),
                         os_type=os_type, os_state=os_state, end_of_life_date=end_of_life_date,
                         recommended=None, disallowed=Disallowed(disk_types=None),
                         purchase_plan=purchase_plan, location=location, eula=None, tags=(tags or {}),
                         hyper_v_generation='V2', features=feature_list, architecture=None)

    poller = client.gallery_images.begin_create_or_update(resource_group_name, gallery_name, gallery_image_name, image)
    result = LongRunningOperation(cmd.cli_ctx)(poller)

    return result
