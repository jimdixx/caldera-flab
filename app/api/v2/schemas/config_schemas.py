import marshmallow as ma
from marshmallow import fields


class ConfigUpdateItemSchema(ma.Schema):
    prop = fields.String(required=True)
    value = fields.String(required=True)

class ConfigUpdateSchema(ma.Schema):
    updates = fields.List(fields.Nested(ConfigUpdateItemSchema), required=True)

class AgentConfigUpdateSchema(ma.Schema):
    sleep_min = fields.Integer()
    sleep_max = fields.Integer()
    watchdog = fields.Integer()
    untrusted_timer = fields.Integer()
    implant_name = fields.String()
    architecture = fields.String()
    bootstrap_abilities = fields.List(fields.String)
    deadman_abilities = fields.List(fields.String)
    deployments = fields.List(fields.String, dump_only=True)
