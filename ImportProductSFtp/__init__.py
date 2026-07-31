"""
ImportProductSFTP.py

Python (Azure Functions) equivalent of ImportProductSFTP.cs.

Supports three operations via JSON request body ("operation" field):
  - "upload"   (default): base64 -> Blob Storage -> pushed to SFTP
  - "download" : pulls a file from SFTP, returns it as base64
  - "list"     : lists files in an SFTP directory

Required packages (requirements.txt):
  azure-functions
  azure-storage-blob
  paramiko
"""

import base64
import io
import json
import logging
import stat

import azure.functions as func
import paramiko
from azure.storage.blob import BlobServiceClient, ContentSettings


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")

    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid or missing JSON body.", status_code=400)

    operation = data.get("operation", "upload")

    blob_storage_connection_string = data.get("BLOBStorageConnectionString")
    storage_account_container = data.get("storageAccountContainer")

    sftp_address = data.get("sftpAddress")
    sftp_port = int(data.get("sftpPort", 22))
    sftp_username = data.get("sftpUsername")
    sftp_password = data.get("sftpPassword")
    sftp_path = data.get("sftpPath")

    if operation.lower() == "download":
        sftp_file_name = data.get("sftpFileName")
        base64_result = download_file_from_sftp(
            sftp_address, sftp_port, sftp_username, sftp_password, sftp_path, sftp_file_name
        )

        if base64_result is not None:
            return func.HttpResponse(
                json.dumps({"fileName": sftp_file_name, "base64": base64_result}),
                mimetype="application/json",
                status_code=200,
            )
        return func.HttpResponse(
            f"Error downloading file '{sftp_file_name}' from SFTP.", status_code=400
        )

    if operation.lower() == "list":
        files = list_files_from_sftp(sftp_address, sftp_port, sftp_username, sftp_password, sftp_path)

        if files is not None:
            return func.HttpResponse(
                json.dumps({"files": files}), mimetype="application/json", status_code=200
            )
        return func.HttpResponse(
            f"Error listing files in SFTP path '{sftp_path}'.", status_code=400
        )

    # Default operation: upload
    base64_string = data.get("base64")
    file_name = data.get("fileName")
    file_type = data.get("fileType")
    file_ext = data.get("fileExt")  # noqa: F841 (kept for parity with original signature)

    uri = upload_blob(
        base64_string, file_name, file_type, file_ext, blob_storage_connection_string, storage_account_container
    )

    # Upload to SFTP
    result_file_name = upload_file_to_sftp(
        uri, file_name, blob_storage_connection_string, storage_account_container,
        sftp_address, sftp_port, sftp_username, sftp_password, sftp_path,
    )

    if result_file_name is not None:
        return func.HttpResponse(f"File {result_file_name} stored. URI = {uri}", status_code=200)
    return func.HttpResponse("Error on input parameter (object)", status_code=400)


def upload_blob(base64_string, file_name, file_type, file_ext,
                 blob_storage_connection_string, storage_account_container):
    """Decode base64 payload and upload it to Azure Blob Storage. Returns the blob URL."""
    file_bytes = base64.b64decode(base64_string)

    blob_service_client = BlobServiceClient.from_connection_string(blob_storage_connection_string)
    container_client = blob_service_client.get_container_client(storage_account_container)

    try:
        container_client.create_container(public_access="blob")
    except Exception:
        # Container already exists — same intent as CreateIfNotExistsAsync in the original C#
        pass

    blob_client = container_client.get_blob_client(file_name)
    blob_client.upload_blob(
        file_bytes,
        overwrite=True,
        content_settings=ContentSettings(content_type=file_type),
    )

    return blob_client.url


def upload_file_to_sftp(uri, target_file_name, storage_connection_string, storage_account_container,
                         sftp_address, sftp_port, sftp_username, sftp_password, sftp_path):
    """Download the blob back into memory, then push it to the SFTP server."""
    try:
        blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
        container_client = blob_service_client.get_container_client(storage_account_container)
        blob_client = container_client.get_blob_client(target_file_name)

        stream = io.BytesIO()
        download_stream = blob_client.download_blob()
        stream.write(download_stream.readall())
        stream.seek(0)

        transport = paramiko.Transport((sftp_address, sftp_port))
        transport.connect(username=sftp_username, password=sftp_password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            sftp.putfo(stream, f"/{sftp_path}/{target_file_name}")
            return target_file_name
        finally:
            sftp.close()
            transport.close()

    except IOError as ioex:
        logging.error(f"Error: {ioex}")
        return None
    except paramiko.ssh_exception.SSHException as ex:
        logging.error(f"Error: {ex}")
        return None
    except Exception as ex:
        logging.error(f"Error: {ex}")
        return None


def download_file_from_sftp(sftp_address, sftp_port, sftp_username, sftp_password, sftp_path, sftp_file_name):
    """Download a file from SFTP and return its contents as a base64 string."""
    try:
        transport = paramiko.Transport((sftp_address, sftp_port))
        transport.connect(username=sftp_username, password=sftp_password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            stream = io.BytesIO()
            sftp.getfo(f"/{sftp_path}/{sftp_file_name}", stream)
            return base64.b64encode(stream.getvalue()).decode("utf-8")
        finally:
            sftp.close()
            transport.close()

    except IOError as ioex:
        logging.error(f"Error: {ioex}")
        return None
    except paramiko.ssh_exception.SSHException as ex:
        logging.error(f"Error: {ex}")
        return None
    except Exception as ex:
        logging.error(f"Error: {ex}")
        return None


def list_files_from_sftp(sftp_address, sftp_port, sftp_username, sftp_password, sftp_path):
    """List non-directory file names in the given SFTP path."""
    try:
        transport = paramiko.Transport((sftp_address, sftp_port))
        transport.connect(username=sftp_username, password=sftp_password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            entries = sftp.listdir_attr(f"/{sftp_path}")
            file_names = [
                entry.filename for entry in entries
                if not stat.S_ISDIR(entry.st_mode)
                and entry.filename not in (".", "..")
            ]
            return file_names
        finally:
            sftp.close()
            transport.close()

    except IOError as ioex:
        logging.error(f"Error: {ioex}")
        return None
    except paramiko.ssh_exception.SSHException as ex:
        logging.error(f"Error: {ex}")
        return None
    except Exception as ex:
        logging.error(f"Error: {ex}")
        return None
