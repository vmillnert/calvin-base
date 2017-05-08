import astnode as ast
import visitor
import astprint
from parser import calvin_parse
from codegen import query


class ExpandRules(object):
    """docstring for ExpandRules"""
    def __init__(self, issue_tracker):
        super(ExpandRules, self).__init__()
        self.issue_tracker = issue_tracker

    def process(self, root):
        self.expanded_rules = {}
        rules = query(root, ast.RuleDefinition)
        seen = [rule.name.ident for rule in rules]
        unresolved = rules
        while True:
            self._replaced = False
            for rule in unresolved[:]:
                rule_resolved = self._expand_rule(rule)
                if rule_resolved:
                    self.expanded_rules[rule.name.ident] = rule.rule
                    unresolved.remove(rule)
            if not unresolved:
                # Done
                break
            if not self._replaced:
                # Give up
                for rule in unresolved:
                    reason = "Cannot expand rule '{}'".format(rule.name.ident)
                    self.issue_tracker.add_error(reason, rule)
                return self.expanded_rules
        # OK, final pass over RuleApply
        applies = query(root, ast.RuleApply)
        for a in applies:
            self._expand_rule(a)
        # FIXME: Run a second pass to catch errors

    def _expand_rule(self, rule):
        self._clean = True
        self.visit(rule.rule)
        return self._clean

    @visitor.on('node')
    def visit(self, node):
        pass

    @visitor.when(ast.Node)
    def visit(self, node):
        pass

    @visitor.when(ast.SetOp)
    def visit(self, node):
        self.visit(node.left)
        self.visit(node.right)

    @visitor.when(ast.UnarySetOp)
    def visit(self, node):
        self.visit(node.rule)

    @visitor.when(ast.Id)
    def visit(self, node):
        self._clean = False
        if node.ident in self.expanded_rules:
            node.parent.replace_child(node, self.expanded_rules[node.ident].clone())
            self._replaced = True


class DeployInfo(object):
    """docstring for DeployInfo"""
    def __init__(self, root, issue_tracker):
        super(DeployInfo, self).__init__()
        self.root = root
        self.issue_tracker = issue_tracker

    def process(self):
        self.requirements = {}
        self.visit(self.root)

    @visitor.on('node')
    def visit(self, node):
        pass

    @visitor.when(ast.Node)
    def visit(self, node):
        if not node.is_leaf():
            map(self.visit, node.children)

    @visitor.when(ast.RuleApply)
    def visit(self, node):
        rule = self.visit(node.rule)
        for t in node.targets:
            self.requirements[t.ident] = rule

    @visitor.when(ast.RulePredicate)
    def visit(self, node):
        pred = {
            "predicate":node.predicate.ident,
            "kwargs":{arg.ident.ident:arg.arg.value for arg in node.args}
        }
        return pred

    @visitor.when(ast.SetOp)
    def visit(self, node):
        rule = {
            "operator":node.op,
            "operands":[self.visit(node.left), self.visit(node.right)]
        }
        return rule

    @visitor.when(ast.UnarySetOp)
    def visit(self, node):
        rule = {
            "operator":node.op,
            "operand":self.visit(node.rule)
        }
        return rule


class DSCodeGen(object):

    verbose = True
    verbose_nodes = False

    """
    Generate code from a deploy script file
    """
    def __init__(self, ast_root, script_name):
        super(DSCodeGen, self).__init__()
        self.root = ast_root
        self.dump_tree('ROOT')

    def dump_tree(self, heading):
        if not self.verbose:
            return
        ast.Node._verbose_desc = self.verbose_nodes
        printer = astprint.BracePrinter()
        print "========\n{}\n========".format(heading)
        printer.process(self.root)


    def generate_code_from_ast(self, issue_tracker):
        er = ExpandRules(issue_tracker)
        er.process(self.root)
        self.dump_tree('EXPANDED')

        gen_deploy_info = DeployInfo(self.root, issue_tracker)
        gen_deploy_info.process()
        return gen_deploy_info.requirements

    def generate_code(self, issue_tracker):
        requirements = self.generate_code_from_ast(issue_tracker)
        self.deploy_info = {'requirements':requirements}
        self.deploy_info['valid'] = (issue_tracker.error_count == 0)


def _calvin_cg(source_text, app_name):
    global global_root
    ast_root, issuetracker = calvin_parse(source_text)
    global_root = ast_root
    cg = DSCodeGen(ast_root, app_name)
    return cg, issuetracker

def calvin_dscodegen(source_text, app_name):
    """
    Generate deployment info from script, return deploy_info and issuetracker.

    Parameter app_name is required to provide a namespace for the application.
    """
    cg, issuetracker = _calvin_cg(source_text, app_name)
    cg.generate_code(issuetracker)
    return cg.deploy_info, issuetracker

