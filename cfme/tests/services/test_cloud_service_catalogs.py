# -*- coding: utf-8 -*-
import fauxfactory
import pytest

from riggerlib import recursive_update
from widgetastic.utils import partial_match

from cfme.common.provider import cleanup_vm
from cfme.cloud.provider import CloudProvider
from cfme.cloud.provider.gce import GCEProvider
from cfme.cloud.provider.azure import AzureProvider
from cfme.services.catalogs.catalog_item import CatalogItem
from cfme.services.service_catalogs import ServiceCatalogs
from cfme import test_requirements
from cfme.utils.generators import random_vm_name
from cfme.utils.log import logger
from cfme.utils.wait import wait_for


pytestmark = [
    test_requirements.service,
    pytest.mark.meta(server_roles="+automate"),
    pytest.mark.tier(2),
    pytest.mark.provider([CloudProvider],
                         required_fields=[['provisioning', 'image']],
                         scope="module"),
]


@pytest.fixture()
def vm_name():
    return random_vm_name(context='provs')


def test_cloud_catalog_item(appliance, vm_name, setup_provider, provider, dialog, catalog, request,
                            provisioning):
    """Tests cloud catalog item

    Metadata:
        test_flag: provision
    """
    wait_for(provider.is_refreshed, func_kwargs=dict(refresh_delta=10), timeout=600)
    request.addfinalizer(lambda: cleanup_vm(vm_name + "0001", provider))
    image = provisioning['image']['name']
    item_name = provider.name + '-service-' + fauxfactory.gen_alphanumeric()

    inst_args = {
        'catalog': {'vm_name': vm_name
                    },
        'environment': {
            'availability_zone': provisioning.get('availability_zone', None),
            'security_groups': [provisioning.get('security_group', None)],
            'cloud_tenant': provisioning.get('cloud_tenant', None),
            'cloud_network': provisioning.get('cloud_network', None),
            'cloud_subnet': provisioning.get('cloud_subnet', None),
            'resource_groups': provisioning.get('resource_group', None)
        },
        'properties': {
            'instance_type': partial_match(provisioning.get('instance_type', None)),
            'guest_keypair': provisioning.get('guest_keypair', None)}
    }
    # GCE specific
    if provider.one_of(GCEProvider):
        recursive_update(inst_args, {
            'properties': {
                'boot_disk_size': provisioning['boot_disk_size'],
                'is_preemptible': True}
        })
    # Azure specific
    if provider.one_of(AzureProvider):
        recursive_update(inst_args, {
            'customize': {
                'admin_username': provisioning['customize_username'],
                'root_password': provisioning['customize_password']}})

    catalog_item = CatalogItem(item_type=provisioning['item_type'],
                               name=item_name,
                               description="my catalog",
                               display_in=True,
                               catalog=catalog,
                               dialog=dialog,
                               catalog_name=image,
                               provider=provider,
                               prov_data=inst_args)
    request.addfinalizer(lambda: catalog_item.delete())
    catalog_item.create()
    service_catalogs = ServiceCatalogs(appliance, catalog_item.catalog, catalog_item.name)
    service_catalogs.order()
    logger.info('Waiting for cfme provision request for service %s', item_name)
    request_description = item_name
    provision_request = appliance.collections.requests.instantiate(request_description,
                                                                   partial_check=True)
    provision_request.wait_for_request()
    assert provision_request.is_succeeded()
