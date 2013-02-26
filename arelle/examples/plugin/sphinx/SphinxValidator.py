'''
sphinxValidator validates Sphinx language expressions in the context of an XBRL DTS and instance.

(c) Copyright 2013 Mark V Systems Limited, California US, All rights reserved.  
Mark V copyright applies to this software, which is licensed according to the terms of Arelle(r).

Sphinx is a Rules Language for XBRL described by a Sphinx 2 Primer 
(c) Copyright 2012 CoreFiling, Oxford UK. 
Sphinx copyright applies to the Sphinx language, not to this software.
Mark V Systems conveys neither rights nor license for the Sphinx language. 
'''

from arelle.ModelValue import QName
from .SphinxParser import (astBinaryOperation, astSourceFile, astNamespaceDeclaration, astRuleBasePreconditions,
                           astNamespaceDeclaration, astStringLiteral, 
                           astHyperspaceExpression, astHyperspaceAxis,
                           astFunctionDeclaration, astFunctionReference, astNode,
                           astPreconditionDeclaration, astPreconditionReference,
                           astFormulaRule, astReportRule, astValidationRule, astWith,
                           namedAxes
                           )

def validate(logMessage, sphinxContext):
    modelXbrl = sphinxContext.modelXbrl
    hasDTS = modelXbrl is not None
    
    # if no formulas loaded, set
    if not hasattr(modelXbrl, "modelFormulaEqualityDefinitions"):
        modelXbrl.modelFormulaEqualityDefinitions = {}
    
    
    if hasDTS:
        import logging
        initialErrorCount = modelXbrl.logCount.get(logging.getLevelName('ERROR'), 0)
        
    sphinxContext.ruleBasePreconditionsNodes = []
    sphinxContext.preconditionNodes = {}
    
    # accumulate definitions
    for prog in sphinxContext.sphinxProgs:
        for node in prog:
            if isinstance(node, astRuleBasePreconditions):
                sphinxContext.ruleBasePreconditionsNodes.append(node)
            elif isinstance(node, astPreconditionDeclaration):
                sphinxContext.preconditionNodes[node.name] = node    
            elif isinstance(node, astFunctionDeclaration):
                sphinxContext.functions[node.name] = node

    # check references            
    def checkNodes(nodes):
        if not nodes: return
        for node in nodes:
            if node is None:
                continue
            elif isinstance(node, (list,set)):
                checkNodes(node)
            elif isinstance(node, astRuleBasePreconditions):
                checkNodes(node.preconditionReferences)
            elif isinstance(node, astPreconditionReference):
                for name in node.names:
                    if name not in sphinxContext.preconditionNodes:
                        logMessage("ERROR", "sphinxCompiler:preconditionReferenceI",
                            _("Precondition reference is not defined %(name)s"),
                            sourceFileLine=node.sourceFileLine,
                            name=name)
            elif isinstance(node, (astFormulaRule, astReportRule, astValidationRule)):
                checkNodes((node.precondition, node.severity, 
                            node.variableAssignments, 
                            node.expr, node.message))
                sphinxContext.rules.append(node)
                if node.severity:
                    severity = node.severity
                    if isinstance(severity, astFunctionReference):
                        severity = severity.name
                    if (severity not in ("error", "warning", "info") and
                        (isinstance(node, astFormulaRule) and severity not in sphinxContext.functions)):
                        logMessage("ERROR", "sphinxCompiler:ruleSeverity",
                            _("Rule %(name)s severity is not recognized: %(severity)s"),
                            sourceFileLine=node.sourceFileLine,
                            name=node.name,
                            severity=node.severity)
                if isinstance(node, astFormulaRule) and not hasFormulaOp(node):
                    logMessage("ERROR", "sphinxCompiler:formulaSyntax",
                        _("Formula %(name)s missing \":=\" operation"),
                        sourceFileLine=node.sourceFileLine,
                        name=node.name)
            elif isinstance(node, astHyperspaceExpression) and hasDTS:
                # check axes
                for axis, value in node.axes.items():
                    if isinstance(axis, QName):
                        concept = modelXbrl.qnameConcepts.get(axis)
                        if concept is None or not concept.isDimensionItem:
                            logMessage("ERROR", "sphinxCompiler:axisNotDimension",
                                _("Axis is not a dimension in the DTS %(qname)s"),
                                sourceFileLine=node.sourceFileLine,
                                qname=axis)
                        elif axis not in sphinxContext.dimensionIsExplicit:
                            sphinxContext.dimensionIsExplicit[axis] = concept.isExplicitDimension
                    if (axis not in {"unit", "segment", "scenario"} and
                        isinstance(value, astHyperspaceAxis) and
                        isinstance(value.restriction, (list, tuple))):
                        for restrictionValue in value.restriction:
                            if isinstance(restrictionValue, QName) and not restrictionValue in modelXbrl.qnameConcepts: 
                                logMessage("ERROR", "sphinxCompiler:axisNotDimension",
                                    _("Hypercube value not in the DTS %(qname)s"),
                                    sourceFileLine=node.sourceFileLine,
                                    qname=restrictionValue)
                        checkNodes(value.whereExpr)
            elif isinstance(node, astWith):
                node.axes = {}
                def checkWithAxes(withNode):
                    if isinstance(withNode, astHyperspaceExpression):
                        checkNodes((withNode,))
                        node.axes.update(withNode.axes)
                    else:
                        logMessage("ERROR", "sphinxCompiler:withRestrictionError",
                            _("With restriction is not a single hyperspace expression"),
                            sourceFileLine=withNode.sourceFileLine)
                checkWithAxes(node.restrictionExpr)
                checkNodes((node.variableAssignments, node.bodyExpr,))
            elif isinstance(node, astNode):
                checkNodes([expr
                            for expr in node.__dict__.values() 
                            if isinstance(expr, (astNode, list, set))])
                
    for prog in sphinxContext.sphinxProgs:
        checkNodes(prog)
                    
    if len(sphinxContext.ruleBasePreconditionsNodes) > 1:
        logMessage("ERROR", "sphinxCompiler:multipleRuleBaseDeclarations",
            _("Multiple rule-base declarations %(preconditions)s"),
            sourceFileLines=[node.sourceFileLine for node in sphinxContext.ruleBasePreconditionsNodes],
            preconditions=", ".join(str(r) for f, r in sphinxContext.ruleBasePreconditionsNodes)) 
        
               

    sphinxContext.ruleBasePreconditionNodes = [sphinxContext.preconditionNodes[name]
                                               for node in sphinxContext.ruleBasePreconditionsNodes
                                               for ref in node.preconditionReferences
                                               for name in ref.names
                                               if name in sphinxContext.preconditionNodes]

    if hasDTS:
        # if no errors in checking sphinx
        if initialErrorCount == modelXbrl.logCount.get(logging.getLevelName('ERROR'), 0):
            from .SphinxEvaluator import evaluateRuleBase
            evaluateRuleBase(sphinxContext)
        
def hasFormulaOp(node):
    if isinstance(node, astBinaryOperation) and node.op == ":=":
        return True
    for exprName in ("expr", "leftExpr", "rightExpr", "bodyExpr"):
        if hasattr(node,exprName):
            if hasFormulaOp( getattr(node, exprName) ):
                return True
    return False