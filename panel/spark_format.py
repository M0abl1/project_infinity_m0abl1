"""Minimal wire-compatible schema for spark execution profiles.

Field numbers follow the public spark_sampler.proto/spark.proto contracts.
Unknown metadata (including server configurations and creator identity) is ignored.
No Java code, pickle, JFR or external viewer is executed.
"""
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


def profile_type():
    file = descriptor_pb2.FileDescriptorProto(name='panel_spark.proto', package='panel_spark', syntax='proto3')
    # name, number, scalar type or message name, repeated
    schemas = {
        'Source': [('name', 1, 9, False), ('version', 2, 9, False)],
        'SourceEntry': [('key', 1, 9, False), ('value', 2, 'Source', False)],
        'StringEntry': [('key', 1, 9, False), ('value', 2, 9, False)],
        'Platform': [('name', 2, 9, False), ('minecraft_version', 4, 9, False), ('spark_version', 9, 9, False)],
        'Metadata': [('start_time', 2, 3, False), ('interval', 3, 5, False),
                     ('platform', 7, 'Platform', False), ('end_time', 11, 3, False),
                     ('sources', 13, 'SourceEntry', True), ('sampler_mode', 15, 5, False)],
        'Node': [('class_name', 3, 9, False), ('method_name', 4, 9, False),
                 ('line_number', 6, 5, False), ('method_desc', 7, 9, False),
                 ('times', 8, 1, True), ('children_refs', 9, 5, True)],
        'Thread': [('name', 1, 9, False), ('children', 3, 'Node', True),
                   ('times', 4, 1, True), ('children_refs', 5, 5, True)],
        'Profile': [('metadata', 1, 'Metadata', False), ('threads', 2, 'Thread', True),
                    ('class_sources', 3, 'StringEntry', True), ('method_sources', 4, 'StringEntry', True),
                    ('line_sources', 5, 'StringEntry', True)],
    }
    for name, fields in schemas.items():
        message = file.message_type.add(name=name)
        for field_name, number, kind, repeated in fields:
            field = message.field.add(name=field_name, number=number, label=3 if repeated else 1,
                                      type=11 if isinstance(kind, str) else kind)
            if isinstance(kind, str):
                field.type_name = '.panel_spark.' + kind
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file)
    return message_factory.GetMessageClass(pool.FindMessageTypeByName('panel_spark.Profile'))


Profile = profile_type()
