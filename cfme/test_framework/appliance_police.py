import attr
import pytest


import requests

from cfme.utils import ports
from cfme.utils.net import net_check
from cfme.utils.wait import TimedOutError
from cfme.utils.conf import rdb

from fixtures.pytest_store import store

from cfme.fixtures.rdb import Rdb


@attr.s
class AppliancePoliceException(Exception):
    message = attr.ib()
    port = attr.ib()

    def __str__(self):
        return "{} (port {})".format(self.message, self.port)


@pytest.fixture(autouse=True, scope="function")
def appliance_police():
    if not store.slave_manager:
        return
    try:
        appliance = store.current_appliance
        available_ports = {
            'ssh': (appliance.hostname, ports.SSH),
            'https': (appliance.hostname, appliance.ui_port),
            'postgres': (appliance.db_host or appliance.hostname, ports.DB)}
        port_results = {pn: net_check(addr=pp[0], port=pp[1], force=True)
                        for pn, pp in available_ports.items()}
        for port, result in port_results.items():
            if port == 'ssh' and appliance.is_pod:
                # ssh is not available for podified appliance
                continue
            if not result:
                raise AppliancePoliceException('Unable to connect', available_ports[port][1])

        try:
            status_code = requests.get(appliance.url, verify=False,
                                       timeout=120).status_code
        except Exception:
            raise AppliancePoliceException('Getting status code failed',
                                           available_ports['https'][1])

        if status_code != 200:
            raise AppliancePoliceException('Status code was {}, should be 200'.format(
                status_code), available_ports['https'][1])
        return
    except AppliancePoliceException as e:
        # special handling for known failure conditions
        if e.port == 443:
            # Lots of rdbs lately where evm seems to have entirely crashed
            # and (sadly) the only fix is a rude restart
            appliance.restart_evm_service(rude=True)
            try:
                appliance.wait_for_web_ui(900)
                store.write_line('EVM was frozen and had to be restarted.', purple=True)
                return
            except TimedOutError:
                pass
        e_message = str(e)
    except Exception as e:
        e_message = str(e)

    # Regardles of the exception raised, we didn't return anywhere above
    # time to call a human
    msg = 'Help! My appliance {} crashed with: {}'.format(appliance.url, e_message)
    store.slave_manager.message(msg)
    if 'appliance_police_recipients' in rdb:
        rdb_kwargs = {
            'subject': 'RDB Breakpoint: Appliance failure',
            'recipients': rdb.appliance_police_recipients,
        }
    else:
        rdb_kwargs = {}
    Rdb(msg).set_trace(**rdb_kwargs)
    store.slave_manager.message('Resuming testing following remote debugging')
