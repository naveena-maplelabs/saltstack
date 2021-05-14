"""
This module have been tested on Cohesity API v1.
:depends: cohesity-management-sdk,
https://github.com/cohesity/management-sdk-python
sdk can be installed using `pip install cohesity-management-sdk`
"""

import copy
import salt.config
import logging

log = logging.getLogger(__name__)

__virtualname__ = "cohesity"


def __virtual__():
    # To force a module not to load return something like:
    return __virtualname__


try:

    from cohesity_management_sdk.controllers.base_controller import BaseController
    from cohesity_management_sdk.cohesity_client import CohesityClient
    from cohesity_management_sdk.exceptions.api_exception import APIException
    from cohesity_management_sdk.models.cancel_protection_job_run_param import (
        CancelProtectionJobRunParam, )
    from cohesity_management_sdk.models.change_protection_job_state_param import (
        ChangeProtectionJobStateParam, )
    from cohesity_management_sdk.models.delete_protection_job_param import (
        DeleteProtectionJobParam, )
    from cohesity_management_sdk.models.environment_register_protection_source_parameters_enum import (
        EnvironmentRegisterProtectionSourceParametersEnum as env_enum, )
    from cohesity_management_sdk.models.protection_job_request_body import (
        ProtectionJobRequestBody, )
    from cohesity_management_sdk.models.recover_task_request import RecoverTaskRequest
    from cohesity_management_sdk.models.register_protection_source_parameters import (
        RegisterProtectionSourceParameters, )
    from cohesity_management_sdk.models.restore_object_details import (
        RestoreObjectDetails, )
    from cohesity_management_sdk.models.run_protection_job_param import (
        RunProtectionJobParam, )
    from cohesity_management_sdk.models.universal_id import UniversalId
    from cohesity_management_sdk.models.update_protection_jobs_state_request_body import (
        UpdateProtectionJobsStateRequestBody, )
    from cohesity_management_sdk.models.vmware_restore_parameters import (
        VmwareRestoreParameters, )

    HAS_LIBS = True

    # Update the user-agent.
    BaseController.global_headers["user-agent"] = "cohesity-salt/1.0.0"
except ImportError:
    HAS_LIBS = False


def _get_client():
    context_key = "{}.cohesity_client".format(__name__)
    __context__ = dict(context_key=None)
    if context_key in __context__:
        return __context__[context_key]
    opts = salt.config.master_config('/etc/salt/master')
    cohesity_config = opts.get("cohesity_config", {})
    cluster_vip = cohesity_config.get("cluster_vip", "")
    c_username = cohesity_config.get("username", "")
    c_password = cohesity_config.get("password", "")
    c_domain = cohesity_config.get("domain", "")
    cohesity_client = CohesityClient(
        cluster_vip=cluster_vip,
        username=c_username,
        password=c_password,
        domain=c_domain,
    )
    __context__[context_key] = cohesity_client
    return cohesity_client


def __virtual__():
    if HAS_LIBS:
        return __virtualname__
    return False, "Could not import the Cohesity SDK modules"


def _get_sd_id(name):
    """
    Function to fetch storage domain available in the cluster.

    : return: storage domain id.
    """
    cohesity_client = _get_client()
    log.info("Getting storage domain with name %s", name)
    resp = cohesity_client.view_boxes.get_view_boxes(names=name)
    if resp:
        return resp[0].id


def _get_policy_id(name):
    """
    Function to fetch policy available in the cluster.

    : return policy id.
    """
    cohesity_client = _get_client()
    log.info("Getting policy with name %s", name)
    resp = cohesity_client.protection_policies.get_protection_policies(
        names=name)
    if resp:
        return resp[0].id


def _get_vmware_source_ids(name, vm_list):
    """
    Function to virtual machines available in the vcenter.

    : return source ids and vcenter id.
    """
    cohesity_client = _get_client()
    source_id_list = []
    parent_id = -1
    log.info("Fetching Vcenter and Vm ids")
    try:
        result = cohesity_client.protection_sources.list_protection_sources_root_nodes(
            environments=env_enum.K_VMWARE)
        for each_source in result:
            endpoint = each_source.registration_info.access_info.endpoint
            v_name = each_source.protection_source.name

            # Check for both endpoint and source name.
            if name in [endpoint, v_name]:
                parent_id = each_source.protection_source.id
        if parent_id == -1:
            log.error("Vcenter %s not available in the cluster", name)
        vms = cohesity_client.protection_sources.list_virtual_machines(
            v_center_id=parent_id, names=vm_list)
        vm_names = copy.deepcopy(vm_list)
        for vm in vms:
            vm_names.remove(vm.name)
            source_id_list.append(vm.id)
        if vm_names:
            log.error(
                "Following list of vms '%s' are not available in vcenter, "
                "please make sure the virtual machine names are correct",
                ",".join(vm_names),
            )
        return parent_id, source_id_list
    except APIException as err:
        log.error(err)
        return -1, []


def register_vcenter(vcenter, username, password):
    """
    Function to fetch register Vmware Vcenter to cohesity cluster.

    CLI Examples:

    .. code-block:: bash

        salt "*" cohesity.register_vcenter vcenter=vcenter_name username=admin password=admin
    """
    try:
        cohesity_client = _get_client()
        existing_sources = cohesity_client.protection_sources.list_protection_sources_root_nodes(
            environment=env_enum.K_VMWARE)
        for source in existing_sources:
            if source.registration_info.access_info.endpoint == vcenter:
                return "Source with name {} is already registered".format(
                    vcenter)
        body = RegisterProtectionSourceParameters()
        body.endpoint = vcenter
        body.environment = env_enum.K_VMWARE
        body.username = username
        body.password = password
        body.vmware_type = "kVCenter"
        cohesity_client.protection_sources.create_register_protection_source(
            body)
        return "Successfully registered Vcenter {}".format(vcenter)
    except APIException as err:
        log.error(err)
        return str(err)


def create_vmware_protection_job(
    job_name,
    vcenter_name,
    sources,
    policy="Gold",
    domain="DefaultStorageDomain",
    pause_job=True,
    timezone="Europe/Berlin",
    description="",
):
    """
    Create Protection Job for VMware Source.

    CLI Examples:

    .. code-block:: bash

        salt "*" cohesity.create_vmware_protection_job job_name=job_name vcenter_name=vcenter_name sources=virtual_machine
        salt "*" cohesity.create_vmware_protection_job job_name=job_name vcenter_name=vcenter_name sources=virtual_machine1,virtualmachine2
        salt "*" cohesity.create_vmware_protection_job job_name=job_name vcenter_name=vcenter_name sources=virtual_machine1,virtualmachine2 policy=Gold domain=DefaultStorageDomain pause_job=True timezone=Europe/Berlin description='Salt Job'
        salt "*" cohesity.create_vmware_protection_job job_name=job_name vcenter_name=vcenter_name sources=virtual_machine1,virtualmachine2 policy=Gold domain=DefaultStorageDomain pause_job=True timezone=Europe/Berlin
    """
    try:
        cohesity_client = _get_client()
        # Check if the job already exists.
        resp = cohesity_client.protection_jobs.get_protection_jobs(
            names=job_name, is_deleted=False)
        if resp and resp[0].name == job_name:
            return "Job with name {} already exists.".format(job_name)
        body = ProtectionJobRequestBody()
        body.name = job_name
        body.description = description
        body.policy_id = _get_policy_id(policy)
        body.timezone = timezone
        body.view_box_id = _get_sd_id(domain)
        body.environment = env_enum.K_VMWARE
        body.pause = True
        body.parent_source_id, body.source_ids = _get_vmware_source_ids(
            vcenter_name, sources.split(","))
        if body.parent_source_id == -1:
            return "Unable to fetch Vcenter with name {}".format(vcenter_name)
        elif len(body.source_ids) == 0:
            return ("Minimum of one VM is required to created protection job."
                    " Unable to find atleast provided VMs {} in the Vcenter {}"
                    .format(",".join(sources), vcenter_name))
        else:
            resp = cohesity_client.protection_jobs.create_protection_job(body)
            if pause_job:
                # Pause the job.
                jobstate_body = ChangeProtectionJobStateParam()
                jobstate_body.pause = pause_job
                cohesity_client.protection_jobs.change_protection_job_state(
                    resp.id, jobstate_body)
            return "Successfully created ProtectionGroup: {}".format(body.name)
    except APIException as err:
        return "Error creating job {} {}".format(job_name, err)


def update_vmware_protection_job(job_name,
                                 vcenter_name,
                                 sources,
                                 replace_existing=True):
    """
    Function to update vmware protection job, updatee virtual machines
    available in the job.

    CLI Examples:

    .. code-block:: bash

        salt "*" cohesity.update_vmware_protection_job job_name=job vcenter_name=vcenter sources=vitual_machine
        salt "*" cohesity.update_vmware_protection_job job_name=job vcenter_name=vcenter sources=vitual_machine replace_existing=True

    """
    try:
        cohesity_client = _get_client()
        resp = cohesity_client.protection_jobs.get_protection_jobs(
            is_deleted=False, names=job_name)
        if not resp:
            return "Job with name {} not available".format(job_name)
        body = resp[0]
        job_id = body.id
        _, new_source_ids = _get_vmware_source_ids(vcenter_name,
                                                   sources.split(","))
        body.source_ids = [] if replace_existing else body.source_ids
        for source_id in new_source_ids:
            if source_id not in body.source_ids:
                body.source_ids.append(source_id)
        cohesity_client.protection_jobs.update_protection_job(body, job_id)
        return "Successfully Updated ProtectionGroup: {}".format(body.name)
    except APIException as err:
        return "Error updating job {} {}".format(job_name, err)


def update_vmware_protection_job_state(job_name, state):
    """
    Function to update protection job state. Job state includes activate,
    deactivate, pause, resume.

    CLI Examples:

    .. code-block:: bash

        salt "*" cohesity.update_vmware_protection_job_state job_name=job state=activate

    """
    try:
        cohesity_client = _get_client()
        jobs = cohesity_client.protection_jobs.get_protection_jobs(
            is_deleted=False, names=job_name)
        if not jobs:
            return "Job with name {} not available.".format(job_name)
        for job in jobs:
            if job.name == job_name:
                job_id = job.id
                break
        body = UpdateProtectionJobsStateRequestBody()
        supported_states = ["activate", "deactivate", "pause", "resume"]
        if state not in supported_states:
            return ("Job state {} not supported. Please provide one of the "
                    "following states {}".format(state,
                                                 ", ".join(supported_states)))
        body.action = "k" + state.capitalize()
        body.job_ids = [job_id]
        cohesity_client.protection_jobs.update_protection_jobs_state(body)
        return "Successfully {}d future run for job {}".format(state, job_name)
    except APIException as err:
        return "Error while attempting to {} the job {} {}".format(
            state, job_name, err)


def cancel_vmware_protection_job(job_name):
    """
    Function to cancel a running protection job.

    CLI Examples:

    .. code-block:: bash

        salt "*" cohesity.cancel_vmware_protection_job job_name=job

    """
    try:
        cohesity_client = _get_client()
        jobs = cohesity_client.protection_jobs.get_protection_jobs(
            is_deleted=False, names=job_name)
        if not jobs:
            return "Job with name {} not available.".format(job_name)
        for job in jobs:
            if job.name == job_name:
                job_id = job.id
                break
        if not job_id:
            return "Job with name {} not available.".format(job_name)

        # Get recent job run id and status.
        runs = cohesity_client.protection_runs.get_protection_runs(
            job_id=job_id)
        if not runs:
            return "Job run details not available for job {}".format(job_name)
        latest_run = runs[0]
        if latest_run.backup_run.status not in ["kRunning", "kAccepted"]:
            return "No active job run available for job {}".format(job_name)
        run_id = latest_run.backup_run.job_run_id
        body = CancelProtectionJobRunParam()
        body.job_run_id = run_id
        cohesity_client.protection_runs.create_cancel_protection_job_run(
            job_id, body)
        return "Successfully cancelled the run for job {}".format(job_name)
    except APIException as err:
        return "Error while attempting to cancel the job {}, error : {}".format(
            job_name, err)


def run_vmware_protection_job(job_name):
    """
    Function to run protection job.

    CLI Examples:

    .. code-block:: bash

        salt "*" cohesity.run_vmware_protection_job job_name=job
    """
    try:
        job_id = None
        cohesity_client = _get_client()
        jobs = cohesity_client.protection_jobs.get_protection_jobs(
            is_deleted=False, names=job_name)
        if not jobs:
            return "Job with name {} not available.".format(job_name)
        for job in jobs:
            if job.name == job_name:
                job_id = job.id
                break
        if not job_id:
            return "Job with name {} not available.".format(job_name)
        # Get recent job run id and status.
        body = RunProtectionJobParam()
        cohesity_client.protection_jobs.create_run_protection_job(job_id, body)
        return "Successfully started run for job {}".format(job_name)
    except APIException as err:
        return "Error while attempting to start the job {}, error : {}".format(
            job_name, err)


def delete_vmware_protection_job(job_name, delete_snapshots=True):
    """
    Function to delete protection job and snapshots.

    CLI Examples:

    .. code-block:: bash

        salt "*" cohesity.delete_vmware_protection_job job_name=job delete_snapshots=False
    """
    try:
        cohesity_client = _get_client()
        jobs = cohesity_client.protection_jobs.get_protection_jobs(
            is_deleted=False, names=job_name)
        if not jobs:
            return "Job with name {} not available.".format(job_name)
        for job in jobs:
            if job.name == job_name:
                job_id = job.id
                break
        if not job_id:
            return "Job with name {} not available.".format(job_name)
        # Get recent job run id and status.
        body = DeleteProtectionJobParam()
        body.delete_snapshots = delete_snapshots
        cohesity_client.protection_jobs.delete_protection_job(job_id, body)
        return "Successfully deleted job {}".format(job_name)
    except APIException as err:
        return "Error while attempting to delete the job {}, error : {}".format(
            job_name, err)


def _fetch_source_objects(source_objects, source_type, name=None):
    """
    Function to fetch source objects by object type.
    """
    try:
        nodes = source_objects[0].nodes
        for node in nodes:
            if node.get("nodes", []):
                nodes.extend(node["nodes"])
            else:
                if node["protectionSource"]["vmWareProtectionSource"][
                        "type"] == source_type:
                    obj_name = node["protectionSource"]["name"]
                    if not name:
                        return node["protectionSource"]["id"]
                    elif name and name == obj_name:
                        return node["protectionSource"]["id"]
    except APIException as err:
        return str(err)


def restore_vms(task_name,
                vcenter_name,
                vm_names,
                resource_pool="",
                datastore_name="",
                prefix="",
                suffix="",
                powered_on=True):
    """
    Function to recover vm.

    CLI Examples:

    .. code-block:: bash

        salt "*" cohesity.restore_vms task_name=task vcenter_name=vcenter vm_names=virtual_machine resource_pool=pool
        salt "*" cohesity.restore_vms task_name=task vcenter_name=vcenter vm_names=virtual_machine resource_pool=pool datastore_name=DS1 prefix='pre-' suffix='_copy' powered_on=True

    """
    try:
        cohesity_client = _get_client()
        body = RecoverTaskRequest()
        body.name = task_name
        parent_id, source_id = _get_vmware_source_ids(vcenter_name,
                                                      vm_names.split(","))
        body.type = "kRecoverVMs"
        body.objects = []
        source_objects = cohesity_client.protection_sources.list_protection_sources(
            id=parent_id,
            include_datastores=True,
            exclude_types=["kHostSystem", "kVirtualMachine"],
            environment=env_enum.K_VMWARE,
        )
        resource_pool_id = _fetch_source_objects(source_objects,
                                                 "kResourcePool",
                                                 resource_pool)
        datastore_id = _fetch_source_objects(source_objects, "kDatastore",
                                             datastore_name)
        # Fetch the latest snapshot details.
        resp = cohesity_client.restore_tasks.search_objects(
            search=vm_names[0],
            environments=env_enum.K_VMWARE,
            registered_source_ids=parent_id,
        )
        snapshots = resp.object_snapshot_info
        timestamp = 0
        restore_obj = RestoreObjectDetails()
        job_uid = UniversalId()
        for each_snapshot in snapshots:
            snapshot_time = each_snapshot.versions[0].started_time_usecs
            if timestamp < snapshot_time:
                job_id = each_snapshot.job_id
                job_run_id = each_snapshot.versions[0].job_run_id
                job_uid = each_snapshot.job_uid
                t_stamp = snapshot_time
                timestamp = snapshot_time
        restore_obj.environment = env_enum.K_VMWARE
        restore_obj.job_id = job_id
        restore_obj.job_run_id = job_run_id
        restore_obj.uid = job_uid
        restore_obj.protection_source_id = source_id[0]
        restore_obj.sourceName = vm_names[0]
        restore_obj.started_time_usecs = t_stamp
        body.objects.append(restore_obj)
        vmware_params = VmwareRestoreParameters()
        vmware_params.powered_on = powered_on
        vmware_params.recovery_process_type = "kInstantRecovery"
        vmware_params.prefix = prefix
        vmware_params.suffix = suffix
        body.vmware_parameters = vmware_params
        cohesity_client.restore_tasks.create_recover_task(body)
        return "Successfully created restore task '{}'.".format(task_name)
    except APIException as err:
        return str(err)
