import warnings
from collections import OrderedDict

from trod import types, errors, utils
from trod.model_ import tables


class _ModelMeta(type):

    def __new__(cls, name, bases, attrs):
        if name in ("_Model", "Model"):
            return type.__new__(cls, name, bases, attrs)

        attrs = cls.__prepare__(name, attrs)
        return type.__new__(cls, name, bases, attrs)

    def __prepare__(cls, name, attrs):
        bound = attrs.pop("__db__", None)
        table_name = attrs.pop("__table__", None)
        if not table_name:
            warnings.warn(
                f"Did not give the table name, use the model name `{name}`",
                errors.ProgrammingWarning
            )
        table_name = name.lower()

        fields = OrderedDict()
        pk = utils.Tdict(auto=False, field=None, ai=None)

        for attr in attrs.copy():
            if pk.field and attr == pk.field.name:
                raise errors.DuplicateFieldNameError(f"Duplicate field name `{attr}`")
            field = attrs.pop(attr)
            if isinstance(field, types.__real__.FieldBase):
                field.name = field.name or attr
                if getattr(field, 'pk', None):
                    if pk.field is not None:
                        raise errors.DuplicatePKError(
                            f"Duplicate primary key found for field {field.name}"
                        )
                    pk.field = field
                    if field.ai:
                        pk.auto = True
                        pk.ai = int(field.ai)
                        if field.name != tables.Table.AIPK:
                            warnings.warn(
                                "The field name of AUTO_INCREMENT primary key is suggested \
                                to use `id` instead of {field.name}",
                                errors.ProgrammingWarning
                            )

                fields[attr] = field
            elif attr not in tables.Table.DEFAULT:
                raise errors.InvalidFieldType(f"Invalid model field {attr}")

        if not pk.field:
            raise errors.NoPKError(
                f"Primary key not found for table `{table_name}`"
            )

        indexes = attrs.pop("__indexes__", ())
        if not isinstance(types.SEQUENCE):
            raise TypeError("")
        for index in indexes:
            if not isinstance(index, types.__real__.IndexBase):
                raise errors.InvalidFieldType()

        attrs['__table__'] = tables.Table(
            database=bound, name=table_name,
            fields=fields, pk=pk, indexes=tuple(indexes),
            charset=attrs.pop('__charset__', None),
            comment=attrs.pop('__comment__', None),
        )
        return attrs

    def __getattr__(cls, key):
        try:
            value = getattr(cls, key)
        except AttributeError:
            if key in cls.__table__.fields_dict:
                value = cls.__table__.fields_dict[key]
            else:
                raise AttributeError(
                    f"'{cls.__name__}' class does not have `{key}` attribute"
                )
        return value

    def __setattr__(cls, _key, _value):
        raise errors.ModelSetAttrError(
            f"'{cls.__name__}' class not allow set attribute")


class _Model(metaclass=_ModelMeta):

    def __init__(self, **kwargs):
        for attr in kwargs:
            setattr(self, attr, kwargs[attr])

    def __repr__(self):
        return "<{0}(table '{1}': {2})>".format(
            self.__class__.__name__, self.__table__.name, self.__table__.comment
        )

    __str__ = __repr__

    def __hash__(self):
        pass

    def __getattr__(self, key):
        try:
            return self.__dict__[key]
        except KeyError:
            if key == self.__table__.pk.field.name or key in self.__table__.fields_dict:
                value = None
            else:
                raise AttributeError(
                    f"'{self.__class__.__name__}' object has no attribute '{key}'"
                )
            return value

    def __setattr__(self, key, value, is_loader=False):
        if self.__table__.pk.auto is True:
            if key == self.__table__.pk.field.name:
                raise errors.ModifyAutoPkError(
                    'AUTO_INCREMENT table not allowed modify primary key'
                )
        if not is_loader and (key not in self.__table__.fields_dict):
            raise AttributeError(
                f"'{self.__class.__name__}' object not allowed set attribute '{key}'"
            )

        self.__dict__[key] = value

    @property
    @utils.tdictformatter
    def __self__(self):
        fields = [f for f in self.__table__.fields]
        values = {}
        for f in fields:
            v = self.__getattr__(f.name)
            if v is None and callable(f):
                v = f()
            if v is not None:
                values[f.name] = v
        return values

    @classmethod
    async def _create_table(cls, **options):
        """ Do create table """

        return await cls.__table__.create(**options)

    @classmethod
    async def _drop_table(cls, **options):
        """ Do drop table """

        return await cls.__table__.drop(**options)

    @classmethod
    def _alter(cls):

        return cls.__table__.show()

    @classmethod
    def _show(cls):

        return cls.__table__.alter()

    @classmethod
    async def _get(cls, _id):

        return await tables.Select(
            cls, cls.__table__.columns
        ).where(
            cls.__table__.fields_dict[cls.__table__.pk.name] == _id
        ).first()

    @classmethod
    async def _get_many(cls, ids, columns=None):

        columns = columns or cls.__table__.columns

        return await tables.Select(
            cls, columns
        ).where(
            cls.__table__.fields_dict[cls.__table__.pk.name].in_(ids)
        ).all()

    @classmethod
    def _add(cls, instance):

        rows = Rows([instance.__self__])
        return tables.Insert(cls.__table__, rows)

    @classmethod
    def _add_many(cls, instances):

        rows = Rows([instance.__self__ for instance in instances])
        return tables.Insert(cls.__table__.name, rows)

    @classmethod
    def _select(cls, *columns, distinct=False):

        columns = columns or cls.__table__.columns
        return tables.Select(cls, columns, distinct=distinct)

    @classmethod
    def _insert(cls, data=None, **kwargs):
        """
        # Using keyword arguments:
        zaizee_id = Person.insert(first='zaizee', last='cat').execute()

        # Using column: value mappings:
        Note.insert({
        Note.person_id: zaizee_id,
        Note.content: 'meeeeowwww',
        Note.timestamp: datetime.datetime.now()}).execute()
        """

        insert_data = data or kwargs
        return tables.Insert(cls.__table__.name, Rows(insert_data))

    @classmethod
    def _insert_many(cls, rows, columns=None):
        """
        people = [
            {'first': 'Bob', 'last': 'Foo'},
            {'first': 'Herb', 'last': 'Bar'},
            {'first': 'Nuggie', 'last': 'Bar'}]

        # Inserting multiple rows returns the ID of the last-inserted row.
        last_id = Person.insert(people).execute()

        # We can also specify row tuples, so long as we tell Peewee which
        # columns the tuple values correspond to:
        people = [
            ('Bob', 'Foo'),
            ('Herb', 'Bar'),
            ('Nuggie', 'Bar')]
        Person.insert(people, columns=[Person.first, Person.last]).execute()
        """

        rows = Rows(rows, columns=columns)
        return tables.Insert(cls.__table__.name, rows)

    @classmethod
    def _update(cls, **values):

        return tables.Update(cls.__table__, values)

    @classmethod
    def _delete(cls):

        return tables.Delete(cls.__table__)

    @classmethod
    def _replace(cls, **values):

        rows = Rows([values])
        return tables.Replace(cls.__table__, rows)

    async def _save(self):
        """ save self """

        rows = Rows([self.__self__])
        result = await tables.Replace(self.__table__.name, rows).do()
        self.__setattr__(self.__table__.name, result.last_id)
        return result

    async def _remove(self):
        """ delete self """

        pk = self.__getattr__(self.__table__.pk.field.name)
        if not pk:
            raise RuntimeError()  # TODO

        return await tables.Delete(
            self.__table__.name
        ).where(self.__table__.pk.field == pk).do()


class Rows:

    def __init__(self, rows, columns=None):
        pass

    @property
    def columns(self):
        pass

    @property
    def values(self):
        pass


class Loader:
    pass


def load(results, model, use_tdict):

    if not results:
        return _empty(results, model, use_tdict)

    if use_tdict:
        return utils.formattdict(results)
    return _load_to_model(results, model)


def _empty(results, model, use_tdict):
    if isinstance(results, dict):
        if use_tdict:
            return utils.Tdict()
        return model()
    if isinstance(results, (list, tuple)):
        if use_tdict:
            return [utils.Tdict()]
        return FetchResult()

    raise ValueError()


def _load_to_model(results, model):

    # TODO func field
    def _do(results, model):
        model = model()
        for key, value in results.items():
            model.set_value(key, value, is_loader=True)
        return model

    if isinstance(results, dict):
        return _do(results, model)
    if isinstance(results, (list, tuple)):
        return FetchResult([_do(r, model) for r in results])

    raise ValueError()


class FetchResult(list):

    def __repr__(self):
        pass

    __str__ = __repr__

    def __iter__(self):
        """ for x in self """
        pass

    def __getitem__(self, idx):
        """ self[key] """
        pass

    def __contains__(self, value):
        """ value in self, value not in self """
        pass


class ExecResults:
    def __init__(self, affected, last_id):
        self.affected = affected
        self.last_id = last_id

    def __repr__(self):
        pass

    __str__ = __repr__
