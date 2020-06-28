"""Basic CRUD operations for the server.

    ===============================
    Imports :

    sqlalchemy.orm.with_polymorphic : Load columns for inheriting classes.
    Ref : http://docs.sqlalchemy.org/en/latest/orm/query.html

    sqlalchemy.exists : A convenience method that turns a query into an EXISTS subquery
    of the form EXISTS (SELECT 1 FROM … WHERE …).
    Ref : http://docs.sqlalchemy.org/en/latest/orm/query.html

    sqlalchemy.orm.exc.NoResultFound : A database result was required but none was found.
    Ref : http://docs.sqlalchemy.org/en/latest/orm/exceptions.html?highlight=result%20found#sqlalchemy.orm.exc.NoResultFound

    sqlalchemy.orm.session.Session : Manages persistence operations for ORM-mapped objects.
    Ref : http://docs.sqlalchemy.org/en/latest/orm/session_api.html?highlight=session#module-sqlalchemy.orm.session

    hydrus.data.db_models.Graph : Model for a graph that store triples of instance from the other models to map relationships.
    hydrus.data.db_models.BaseProperty : Model for Basic Property.
    hydrus.data.db_models.RDFClass : Model for Classes specifically RDF-OWL or RDF-HYDRA classes.
    hydrus.data.db_models.Instance : Model for Object/Resource. Instances are instances of some kind/classes that are served through the API.
    hydrus.data.db_models.Terminal : Model for Terminals which are numbers or string that can be referenced by a Property.
    hydrus.data.db_models.GraphIAC : Graph model for Instance >> AbstractProperty >> Class.
    hydrus.data.db_models.GraphIIT : Graph model for Instance >> InstanceProperty >> Terminal.
    hydrus.data.db_models.GraphIII : Graph model for Instance >> InstanceProperty >> Instance.

    Ref : ./db_models.py

    hydrus.data.exceptions : Contains all exceptions .
    typing : Module which provides support for type hints .

"""  # nopep8
import re
import copy
from sqlalchemy.orm import with_polymorphic
from sqlalchemy import exists
from sqlalchemy.orm.exc import NoResultFound
from hydrus.data.db_models import Modification
from hydrus.data.exceptions import (
    ClassNotFound,
    InstanceExists,
    PropertyNotFound,
    NotInstanceProperty,
    NotAbstractProperty,
    InstanceNotFound,
    PageNotFound,
    IncompatibleParameters,
    OffsetOutOfRange)
from hydrus.data.crud_helpers import (
    recreate_iri,
    attach_hydra_view,
    pre_process_pagination_parameters,
    get_rdf_class,
    get_data_iac_iii_iit,
    add_prop_name_to_object,
    get_instance_before_delete)
# from sqlalchemy.orm.session import Session
from sqlalchemy.orm.scoping import scoped_session
from typing import Dict, Optional, Any, List

from hydrus.data.resource_based_classes import (
    get_object,
    insert_object,
    update_object,
    delete_object,
    get_all_filtered_instances,
    get_single_response,
    get_database_class
)


def get(id_: str, type_: str, api_name: str, session: scoped_session,
        path: str = None) -> Dict[str, str]:
    """Retrieve an Instance with given ID from the database [GET].
    :param id_: id of object to be fetched
    :param type_: type of object
    :param api_name: name of api specified while starting server
    :param session: sqlalchemy scoped session
    :param path: endpoint
    :return: response to the request


    Raises:
        ClassNotFound: If the `type_` is not a valid/defined RDFClass.
        InstanceNotFound: If no Instance of the 'type_` class if found.

    """
    query_info = {
        "@type": type_,
        "id_": id_
    }
    object_template = get_object(query_info, session)
    if path is not None:
        object_template["@id"] = f"/{api_name}/{path}Collection/{id_}"
    else:
        object_template["@id"] = f"/{api_name}/{type_}Collection/{id_}"

    return object_template


def insert(object_: Dict[str, Any], session: scoped_session, link_props: Dict[str, Any]={},
           id_: Optional[str] = None) -> str:
    """Insert an object to database [POST] and returns the inserted object.
    :param object_: object to be inserted
    :param link_props: Hydra link properties in the object.
    :param session: sqlalchemy scoped session
    :param id_: id of the object to be inserted (optional param)
    :return: ID of object inserted


    Raises:
        ClassNotFound: If `object_["@type"] is not a valid/defined RDFClass.
        InstanceExists: If an Instance `id_` already exists.
        PropertyNotFound: If any property name of `object_` other than `@type` or `@context`
            is not a valid/defined property.
        NotInstanceProperty: If any property of `object_` is a dictionary but
            not an Instance property
        NotAbstractProperty: If any property of `object_` is a
            valid/defined RDFClass but is not a dictionary neither an Abstract Property
    """
    object_template = copy.deepcopy(object_)
    if id_ is not None:
        object_template['id'] = id_
    inserted_object_id = insert_object(object_template, session)
    return inserted_object_id


def insert_multiple(objects_: List[Dict[str,
                                        Any]],
                    session: scoped_session,
                    link_props_list: List[Dict[str, Any]]=[],
                    id_: Optional[str] = "") -> List[str]:
    """
    Adds a list of object with given ids to the database
    :param objects_: List of dict's to be added to the database
    :param session: scoped session from getSession in utils
    :param link_props_list: List of link properties for each object being inserted.
    :param id_: optional parameter containing the ids of objects that have to be inserted
    :return: Ids that have been inserted

    Raises:
        ClassNotFound: If any dict of `objects_` is not a valid/defined RDFClass.
        InstanceExists: If an Instance with same id already exists.
        PropertyNotFound: If for any dict in 'objects_' if any property is not
            a valid/defined property.
        NotAnInstanceProperty: If any property of a dict in `object_` is a dictionary but
            not an Instance property
        NotAnAbstractProperty: If any property of a dict in `object_` is a
            valid/defined RDFClass but is not a dictionary neither an Abstract Property

    """
    # import pdb;pdb.set_trace()

    id_list = id_.split(',')

    # list to hold all the ids of inserted objects
    instance_id_list = list()

    for index in range(len(objects_)):
        link_props_of_object_ = dict()
        id_of_object_ = None
        object_ = objects_[index]
        # check if link_props exist for object at that index
        try:
            link_props_of_object_ = link_props_list[index]
        except IndexError:
            pass
        # check if id_ exist for object at that index
        try:
            id_of_object_ = id_list[index]
        except IndexError:
            pass
        inserted_object_id = insert(object_, session, link_props_of_object_, id_of_object_)
        instance_id_list.append(inserted_object_id)

    return instance_id_list


def delete(id_: str, type_: str, session: scoped_session) -> None:
    """Delete an Instance and all its relations from DB given id [DELETE].
    :param id_: id of object to be deleted
    :param type_: type of object to be deleted
    :param session: sqlalchemy scoped session

    Raises:
        ClassNotFound: If `type_` does not represent a valid/defined RDFClass.
        InstanceNotFound: If no instace of type `type_` with id `id_` exists.

    """
    query_info = {
        "@type": type_,
        "id_": id_
    }
    delete_object(query_info, session)


def delete_multiple(
        id_: List[int],
        type_: str,
        session: scoped_session) -> None:
    """
    To delete multiple rows in a single request
    :param id_: list of ids for objects to be deleted\
    :param type_: type of object to be deleted
    :param session: sqlalchemy scoped session

    Raises:
        ClassNotFound: If `type_` does not represent a valid/defined RDFClass.
        InstanceNotFound: If any instance with type 'type_' and any id in 'id_' list
            does not exist.

    """
    id_list = id_.split(',')
    for object_id_ in id_list:
        delete(object_id_, type_, session)


def update(id_: str,
           type_: str,
           object_: Dict[str,
                         str],
           session: scoped_session,
           api_name: str,
           link_props: Dict[str, Any]={},
           path: str = None) -> str:
    """Update an object properties based on the given object [PUT].
    :param id_: if of object to be updated
    :param type_: type of object to be updated
    :param object_: object that has to be inserted
    :param session: sqlalchemy scoped session
    :param api_name: api name specified while starting server
    :param link_props: Link properties of the object being updated.
    :param path: endpoint
    :return: id of updated object
    """
    query_info = {
        "@type": type_,
        "id_": id_
    }
    updated_object_id = update_object(object_, query_info, session)
    return updated_object_id


def get_collection(API_NAME: str,
                   type_: str,
                   session: scoped_session,
                   paginate: bool,
                   page_size: int,
                   search_params: Dict[str, Any]=None,
                   path: str = None) -> Dict[str, Any]:
    """Retrieve a type of collection from the database.
    :param API_NAME: api name specified while starting server
    :param type_: type of object to be updated
    :param session: sqlalchemy scoped session
    :param paginate: Enable/disable pagination
    :param page_size: Number maximum elements showed in a page
    :param search_params: Query parameters
    :param path: endpoint
    :return: response containing a page of the objects of that particular type_

    Raises:
        ClassNotFound: If `type_` does not represent a valid/defined RDFClass.

    """
    collection_template = {
        "@id": f"/{API_NAME}/{path}/",
        "@context": None,
        "@type": f"{type_}Collection",
        "members": list()
    }  # type: Dict[str, Any]
    filtered_instances = get_all_filtered_instances(session, search_params, type_)
    result_length = len(filtered_instances)
    try:
        # To paginate, calculate offset and page_limit values for pagination of search results
        page, page_size, offset = pre_process_pagination_parameters(search_params=search_params,
                                                                    paginate=paginate,
                                                                    page_size=page_size,
                                                                    result_length=result_length)
    except (IncompatibleParameters, PageNotFound, OffsetOutOfRange):
        raise
    current_page_size = page_size
    if result_length - offset < page_size:
        current_page_size = result_length - offset
    for i in range(offset, offset+current_page_size):
        if path is not None:
            object_template = {
                "@id": f"/{API_NAME}/{path}/{filtered_instances[i].id}",
                "@type": type_
            }
        else:
            object_template = {
                "@id": f"/{API_NAME}/{type_}Collection/{filtered_instances[i].id}",
                "@type": type_
            }
        collection_template["members"].append(object_template)

    # If pagination is disabled then stop and return the collection template
    if paginate is False:
        return collection_template
    collection_template["hydra:totalItems"] = result_length
    # Calculate last page number
    if result_length != 0 and result_length % page_size == 0:
        last = result_length // page_size
    else:
        last = result_length // page_size + 1
    if page < 1 or page > last:
        raise PageNotFound(str(page))
    recreated_iri = recreate_iri(API_NAME, path, search_params=search_params)
    # Decide which parameter to use to provide navigation
    if "offset" in search_params:
        paginate_param = "offset"
    elif "pageIndex" in search_params:
        paginate_param = "pageIndex"
    else:
        paginate_param = "page"
    attach_hydra_view(collection_template=collection_template, paginate_param=paginate_param,
                      result_length=result_length, iri=recreated_iri, page_size=page_size,
                      offset=offset, page=page, last=last)
    return collection_template


def get_single(type_: str, api_name: str, session: scoped_session,
               path: str = None) -> Dict[str, Any]:
    """Get instance of classes with single objects.
    :param type_: type of object to be updated
    :param api_name: api name specified while starting server
    :param session: sqlalchemy scoped session
    :param path: endpoint
    :return: response containing information about a single object

    Raises:
        ClassNotFound: If `type_` does not represt a valid/defined RDFClass.
        InstanceNotFound: If no Instance with type `type_` exists.

    """
    instance = get_single_response(session, type_)
    object_ = get(instance.id, type_, session=session, api_name=api_name, path=path)
    if path is not None:
        object_["@id"] = f"/{api_name}/{path}"
    else:
        object_["@id"] = f"/{api_name}/{type_}"
    return object_


def insert_single(object_: Dict[str, Any], session: scoped_session) -> Any:
    """Insert instance of classes with single objects.
    :param object_: object to be inserted
    :param session: sqlalchemy scoped session
    :return:

    Raises:
        ClassNotFound: If `type_` does not represt a valid/defined RDFClass.
        Instance: If an Instance of type `type_` already exists.

    """
    type_ = object_["@type"]
    database_class = get_database_class(type_)

    try:
        session.query(database_class).all()[-1]
    except (NoResultFound, IndexError, ValueError):
        return insert(object_, session=session)

    raise InstanceExists(type_)


def update_single(object_: Dict[str,
                                Any],
                  session: scoped_session,
                  api_name: str,
                  link_props: Dict[str, Any],
                  path: str = None) -> int:
    """Update instance of classes with single objects.
    :param object_: new object
    :param session: sqlalchemy scoped session
    :param api_name: api name specified while starting server
    :param link_props: Link properties of the object being updated
    :param path: endpoint
    :return: id of the updated object

    Raises:
        ClassNotFound: If `object['@type']` does not represt a valid/defined RDFClass.
        InstanceNotFound: If no Instance of the class exists.

    """
    type_ = object_["@type"]
    instance = get_single_response(session, type_)

    return update(
        id_=instance.id,
        type_=type_,
        object_=object_,
        session=session,
        api_name=api_name,
        link_props=link_props,
        path=path)


def delete_single(type_: str, session: scoped_session) -> None:
    """Delete instance of classes with single objects.
    :param type_: type of object to be deleted
    :param session: sqlalchemy scoped session
    :return: None

    Raises:
        ClassNotFound: If `type_` does not represt a valid/defined RDFClass.
        InstanceNotFound: If no Instance of the class exists.

    """
    instance = get_single_response(session, type_)

    return delete(instance.id, type_, session=session)


def insert_modification_record(method: str, resource_url: str,
                               session: scoped_session) -> int:
    """
    Insert a modification record into the database.
    :param method: HTTP method type of related operation.
    :param resource_url: URL of resource modified.
    :param session: sqlalchemy session.
    :return: ID of new modification record.
    """
    modification = Modification(method=method, resource_url=resource_url)
    session.add(modification)
    session.commit()
    return modification.job_id


def get_last_modification_job_id(session: scoped_session) -> str:
    """
    Get job id of most recent modification record stored in the db.
    :param session: sqlalchemy session
    :return: job id of recent modification.
    """
    last_modification = session.query(Modification).order_by(Modification.job_id.desc()).first()
    if last_modification is None:
        last_job_id = ""
    else:
        last_job_id = last_modification.job_id
    return last_job_id


def get_modification_table_diff(session: scoped_session,
                                agent_job_id: str = None) -> List[Dict[str, Any]]:
    """
    Get modification table difference.
    :param session: sqlalchemy session.
    :param agent_job_id: Job id from the client.
    :return: List of all modifications done after job with job_id = agent_job_id.
    """
    # If agent_job_id is not given then return all the elements.
    if agent_job_id is None:
        modifications = session.query(Modification).order_by(
            Modification.job_id.asc()).all()
    # If agent_job_id is given then return all records which are older
    # than the record with agent_job_id.
    else:
        try:
            record_for_agent_job_id = session.query(Modification).filter(
                Modification.job_id == agent_job_id).one()
        except NoResultFound:
            return []
        modifications = session.query(Modification).filter(
            Modification.job_id > record_for_agent_job_id.job_id).order_by(
            Modification.job_id.asc()).all()

    # Create response body
    list_of_modification_records = []
    for modification in modifications:
        modification_record = {
            "job_id": modification.job_id,
            "method": modification.method,
            "resource_url": modification.resource_url
        }
        list_of_modification_records.append(modification_record)
    return list_of_modification_records
