# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import json
from time import sleep

from azure.cli.core.commands import LongRunningOperation, upsert_to_collection
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.profiles import ResourceType, get_sdk
from azure.cli.core.util import (find_child_item, is_guid, random_string,
                                 sdk_no_wait)
from azure.core.exceptions import ResourceNotFoundError
from azure.mgmt.core.tools import (is_valid_resource_id, parse_resource_id,
                                   resource_id)
from knack.log import get_logger
from knack.util import CLIError
from msrestazure.tools import parse_resource_id, resource_id

from ._client_factory import cf_compute, cf_msi, cf_network, cf_resources

logger = get_logger(__name__)


# def _add_project_role(role, cmd, resource_group_name, project_name, user_id='me'):
#     from azure.cli.command_modules.role.custom import create_role_assignment
#     # client = devcenter_client_factory(cmd.cli_ctx)
#     # project = client.projects.get(resource_group_name, project_name)

#     if user_id.lower() == 'me':
#         from azure.cli.core._profile import Profile
#         user_id = Profile(cli_ctx=cmd.cli_ctx).get_current_account_user()
#         return create_role_assignment(cmd, role=role, assignee=user_id, scope=project.id)

#     if is_guid(user_id):
#         return create_role_assignment(cmd, role=role, assignee_object_id=user_id,
#                                       assignee_principal_type='ServicePrincipal', scope=project.id)

#     return create_role_assignment(cmd, role=role, assignee=user_id, scope=project.id)

def ensure_gallery_permissions(cmd, gallery_id, identity_id):
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
        logger.warning('Identity %s does not have permissions to access the Gallery Resource Group %s. '
                       'Granting permissions...', i_name, g_rg)

        try:
            from azure.cli.command_modules.role.custom import \
                create_role_assignment
            create_role_assignment(cmd, role='Contributor', assignee_object_id=identity.principal_id,
                                   scope=g_rgid, assignee_principal_type='ServicePrincipal')
        except:
            raise CLIError('Failed to grant permissions to the identity. '
                           'Please ensure the identity has Contributor or Owner permissions on the gallery resource group.')

    return identity.principal_id


def get_gallery(cmd, resource_group_name, gallery_name):
    client = cf_compute(cmd.cli_ctx)
    try:
        gallery = client.galleries.get(resource_group_name, gallery_name)
        return gallery
    except ResourceNotFoundError:
        logger.warning('Gallery %s not found in resource group %s', gallery_name, resource_group_name)
        return None


def get_image_definition(cmd, resource_group_name, gallery_name, gallery_image_name):
    client = cf_compute(cmd.cli_ctx)
    try:
        definition = client.gallery_images.get(resource_group_name, gallery_name, gallery_image_name)
        return definition
    except ResourceNotFoundError:
        logger.warning('Image Definitions %s not found in gallery %s', gallery_image_name, gallery_name)
        return None


def get_image_version(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name):
    client = cf_compute(cmd.cli_ctx)
    try:
        version = client.gallery_image_versions.get(resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name)
        return version
    except ResourceNotFoundError:
        logger.warning('Image Version %s not found in image definition %s', gallery_image_version_name, gallery_image_name)
        return None


def image_version_exists(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name):
    return get_image_version(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name) is not None


def create_image_definition(cmd, resource_group_name, gallery_name, gallery_image_name, publisher, offer, sku, location=None, os_type='Windows', os_state='Generalized', end_of_life_date=None, description=None, tags=None):
    logger.warning(f'Creating image definition {gallery_image_name} in gallery {gallery_name}')

    if location is None:
        location = get_gallery(cmd, resource_group_name, gallery_name).location

    client = cf_compute(cmd.cli_ctx)
    GalleryImage, GalleryImageIdentifier, RecommendedMachineConfiguration, ResourceRange, Disallowed, ImagePurchasePlan, GalleryImageFeature = cmd.get_models(
        'GalleryImage', 'GalleryImageIdentifier', 'RecommendedMachineConfiguration', 'ResourceRange', 'Disallowed', 'ImagePurchasePlan', 'GalleryImageFeature',
        resource_type=ResourceType.MGMT_COMPUTE, operation_group='galleries')
    purchase_plan = None
    # if any([plan_name, plan_publisher, plan_product]):
    #     purchase_plan = ImagePurchasePlan(name=plan_name, publisher=plan_publisher, product=plan_product)
    feature_list = [
        GalleryImageFeature(name='SecurityType', value='TrustedLaunch')
    ]

    image = GalleryImage(identifier=GalleryImageIdentifier(publisher=publisher, offer=offer, sku=sku),
                         os_type='Windows', os_state='Generalized', end_of_life_date=None,
                         recommended=None, disallowed=Disallowed(disk_types=None),
                         purchase_plan=purchase_plan, location=location, eula=None, tags=(tags or {}),
                         hyper_v_generation='V2', features=feature_list, architecture=None)
    return client.gallery_images.begin_create_or_update(resource_group_name, gallery_name, gallery_image_name, image)


# def ensure_image_definition(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name):
#     # , location, identity_id, source_image_id, os_type, os_state, os_snapshot_id, data_disk_snapshots, tags=None):
#     client = cf_compute(cmd.cli_ctx)
#     gallery = client.galleries.get(resource_group_name, gallery_name)

#     if not gallery:
#         raise CLIError('Could not find gallery')

#     try:
#         definition = client.gallery_images.get(resource_group_name, gallery.name, 'VSCodeBox')
#         if not definition:
#             raise CLIError('Could not find definition')
#     except ResourceNotFoundError:
#         GalleryImage, GalleryImageIdentifier, RecommendedMachineConfiguration, ResourceRange, Disallowed, ImagePurchasePlan, GalleryImageFeature = cmd.get_models(
#             'GalleryImage', 'GalleryImageIdentifier', 'RecommendedMachineConfiguration', 'ResourceRange', 'Disallowed', 'ImagePurchasePlan', 'GalleryImageFeature',
#             resource_type=ResourceType.MGMT_COMPUTE)
#         purchase_plan = None
#         # if any([plan_name, plan_publisher, plan_product]):
#         #     purchase_plan = ImagePurchasePlan(name=plan_name, publisher=plan_publisher, product=plan_product)
#         feature_list = [
#             GalleryImageFeature(name='SecurityType', value='TrustedLaunch')
#         ]

#         image = GalleryImage(identifier=GalleryImageIdentifier(publisher=publisher, offer=offer, sku=sku),
#                              os_type='Windows', os_state='Generalized', end_of_life_date=None,
#                              recommended=None, disallowed=Disallowed(disk_types=disallowed_disk_types),
#                              purchase_plan=purchase_plan, location=location, eula=eula, tags=(tags or {}),
#                              hyper_v_generation='V2', features=feature_list, architecture=architecture)

#         return 'TODO: Create definition'

#     try:
#         version = client.gallery_image_versions.get(resource_group_name, gallery.name, definition.name, '1.0.1')
#         if not version:
#             raise CLIError('Could not find version')
#     except ResourceNotFoundError:
#         return 'TODO: Create version'
