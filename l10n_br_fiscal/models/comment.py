# Copyright (C) 2019  Renato Lima - Akretion
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

import copy
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools
from odoo.osv import expression

from ..constants.fiscal import (
    COMMENT_TYPE,
    COMMENT_TYPE_COMMERCIAL,
    FISCAL_COMMENT_OBJECTS,
)


class Comment(models.Model):
    _name = "l10n_br_fiscal.comment"
    _description = "Fiscal Comment"
    _order = "sequence"
    _rec_name = "comment"

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    name = fields.Char(
        string="Name",
        required=True,
    )

    comment = fields.Text(
        string="Comment",
        required=True,
    )

    test_comment = fields.Text(
        string="Test Comment",
    )

    comment_type = fields.Selection(
        selection=COMMENT_TYPE,
        string="Comment Type",
        default=COMMENT_TYPE_COMMERCIAL,
        required=True,
    )

    object = fields.Selection(
        selection=FISCAL_COMMENT_OBJECTS,
        string="Object",
        required=True,
    )

    date_begin = fields.Date(
        string="Initial Date",
    )

    date_end = fields.Date(
        string="Final Date",
    )

    object_id = fields.Reference(
        string="Reference",
        selection=FISCAL_COMMENT_OBJECTS,
        ondelete="set null",
    )

    @api.model
    def _name_search(
        self, name, args=None, operator="ilike", limit=100, name_get_uid=None
    ):
        args = args or []
        domain = []
        if name:
            domain = [
                "|",
                ("name", operator, name),
                ("comment", "ilike", "%" + name + "%"),
            ]
        recs = self._search(
            expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid
        )

        return self.browse(recs).name_get()

    def name_get(self):
        def truncate_name(name):
            if len(name) > 60:
                name = "{}...".format(name[:60])
            return name

        return [(r.id, "{}".format(truncate_name(r.name))) for r in self]

    # format_amount function for fiscal observation
    # This way we can format numbers in currency template on fiscal observation
    # msg We'll call this function when setting the variables env below
    def format_amount(self, env, amount, currency):
        fmt = "%.{}f".format(currency.decimal_places)
        lang = env["res.lang"]._lang_get("pt_BR")

        formatted_amount = (
            lang.format(fmt, currency.round(amount), grouping=True, monetary=True)
            .replace(r" ", u"\N{NO-BREAK SPACE}")
            .replace(r"-", u"-\N{ZERO WIDTH NO-BREAK SPACE}")
        )

        pre = post = u""
        if currency.position == "before":
            pre = u"{symbol}\N{NO-BREAK SPACE}".format(symbol=currency.symbol or "")
        else:
            post = u"\N{NO-BREAK SPACE}{symbol}".format(symbol=currency.symbol or "")

        return u"{pre}{0}{post}".format(formatted_amount, pre=pre, post=post)

    def compute_message(self, vals, manual_comment=None):

        if not self.ids and not manual_comment:
            return False

        from jinja2.sandbox import SandboxedEnvironment

        mako_template_env = SandboxedEnvironment(
            block_start_string="<%",
            block_end_string="%>",
            variable_start_string="${",
            variable_end_string="}",
            comment_start_string="<%doc>",
            comment_end_string="</%doc>",
            line_statement_prefix="%",
            line_comment_prefix="##",
            trim_blocks=True,  # do not output newline after
            autoescape=True,  # XML/HTML automatic escaping
        )
        mako_template_env.globals.update(
            {
                "str": str,
                "datetime": datetime,
                "len": len,
                "abs": abs,
                "min": min,
                "max": max,
                "sum": sum,
                "filter": filter,
                "map": map,
                "round": round,
                # dateutil.relativedelta is an old-style class and cannot be
                # instanciated wihtin a jinja2 expression, so a lambda "proxy" is
                # is needed, apparently.
                "relativedelta": lambda *a, **kw: relativedelta.relativedelta(*a, **kw),
                # adding format amount
                # now we can format values like currency on fiscal observation
                "format_amount": (
                    lambda amount, context=self._context: self.format_amount(
                        self.env, amount, self.env.ref("base.BRL")
                    )
                ),
            }
        )
        mako_safe_env = copy.copy(mako_template_env)
        mako_safe_env.autoescape = False

        comments = [manual_comment] if manual_comment else []
        for record in self:
            template = mako_safe_env.from_string(tools.ustr(record.comment))
            comments.append(template.render(vals))
        return " - ".join(comments)

    def action_test_message(self):
        vals = {"user": self.env.user, "ctx": self._context, "doc": self.object_id}
        self.test_comment = self.compute_message(vals)
