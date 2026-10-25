"""R22: syntax evidence, not execution of map code."""
import pytest
import war3_jass as jass


def program(body,header='nothing',returns='nothing'):
    return jass.parse_jass(f'function Test takes {header} returns {returns}\n{body}\nendfunction\n')


def test_strings_comments_and_rawcodes_do_not_create_fake_calls():
    p=program('local string s = "call CustomDefeatBJ(p, \\"fake\\")" // fake call\n'
              'call DisplayTextToPlayer(p, 0, 0, "中文\\n路径\\\\file")\n'
              "set id = 'H600'")
    body=p.functions['Test'].body
    assert [s.kind for s in body]==['local','call','set']
    assert body[0].exprs[0].value=='call CustomDefeatBJ(p, "fake")'
    assert body[1].exprs[0].args[-1].value=='中文\n路径\\file'
    assert body[2].exprs[1].kind=='rawcode' and body[2].exprs[1].value=='H600'


def test_precedence_negation_comparison_and_early_return_preserved():
    p=program('if not (a >= 4 and b == true) or c != 0 then\nreturn false\nendif\nreturn true',returns='boolean')
    condition=p.functions['Test'].body[0].exprs[0]
    assert condition.kind=='binary' and condition.value=='or'
    assert condition.args[0].kind=='unary' and condition.args[0].value=='not'
    assert condition.args[0].args[0].value=='and'
    assert condition.args[0].args[0].args[0].value=='>='
    assert p.functions['Test'].body[0].body[0].exprs[0].value is False
    assert p.functions['Test'].body[-1].exprs[0].value is True


def test_function_arguments_globals_arrays_and_native_type_declarations():
    p=jass.parse_jass('type thing extends handle\n'
        'native External takes integer n returns boolean\n'
        'globals\nconstant integer LIMIT = $FF\nquest array tasks\nendglobals\n'
        'function Test takes integer i, quest q returns nothing\n'
        'set tasks[i + 1] = q\ncall TriggerAddAction(t, function Handler)\nendfunction\n')
    assert p.types==(('thing','handle'),) and 'External' in p.natives
    assert p.globals[0].constant and p.globals[0].exprs[0].value=='$FF'
    assert p.globals[1].array and p.globals[1].type_name=='quest'
    f=p.functions['Test'];assert f.params==( ('integer','i'),('quest','q') )
    assert f.body[0].exprs[0].kind=='index'
    assert f.body[1].exprs[0].args[1].kind=='function_ref'
    assert f.body[1].exprs[0].args[1].value=='Handler'


def test_elseif_else_loop_exitwhen_and_debug_are_not_flattened():
    p=program('loop\nexitwhen i > 3\nif i == 1 then\nset x = 1\n'
        'elseif i == 2 then\nset x = 2\nelse\ndebug call D()\nendif\nendloop')
    loop=p.functions['Test'].body[0]
    assert loop.kind=='loop' and loop.body[0].kind=='exitwhen'
    branch=loop.body[1];assert branch.kind=='if' and branch.body[0].kind=='set'
    assert branch.otherwise[0].kind=='if'
    assert branch.otherwise[0].otherwise[0].kind=='debug'


def test_line_and_column_positions_survive_bom_crlf_and_comments():
    p=jass.parse_jass('\ufeff// comment\r\nfunction Test takes nothing returns nothing\r\n'
        '    call CustomDefeatBJ(Player(0), "bad") // text\r\nendfunction\r\n')
    f=p.functions['Test'];call=f.body[0]
    assert f.line==2 and f.end_line==4
    assert call.line==3 and call.exprs[0].column==10


def test_arithmetic_and_real_hex_null_values_are_retained():
    p=program('set x = -1 + 2 * 3 / .5\nset y = 0x10\nset q = null')
    body=p.functions['Test'].body
    assert body[0].exprs[1].value=='+' and body[0].exprs[1].args[1].value=='/'
    assert body[1].exprs[1].value=='0x10'
    assert body[2].exprs[1].kind=='null'


@pytest.mark.parametrize('body',[
    'call Bad("unterminated)', 'set x = (1 + 2', 'set x = 1 garbage',
    'if true then\ncall F()', 'loop\ncall F()', 'call 123',
    "set x = 'abc'", 'call F()\nunknown_statement',
])
def test_malformed_or_unsupported_input_cannot_be_a_success(body):
    with pytest.raises(jass.JassParseError): program(body)


def test_duplicate_function_does_not_silently_replace_definition():
    s='function F takes nothing returns nothing\nendfunction\n'
    with pytest.raises(jass.JassParseError,match='重复'): jass.parse_jass(s+s)


def test_cancellation_and_limits_fail_explicitly(monkeypatch):
    with pytest.raises(jass.JassParseError,match='取消'): jass.parse_jass('',lambda:True)
    monkeypatch.setattr(jass,'MAX_TOKENS',8)
    with pytest.raises(jass.JassParseError,match='上限'): program('call F(1,2,3)')


def test_nesting_limit_raises_domain_error_instead_of_python_recursion(monkeypatch):
    monkeypatch.setattr(jass,'MAX_NESTING',8)
    with pytest.raises(jass.JassParseError,match='上限'): program('set x = '+'('*10+'1'+')'*10)


def test_empty_script_is_not_a_syntactic_error_but_lua_is_rejected():
    assert not jass.parse_jass('// empty\n').functions
    with pytest.raises(jass.JassParseError): jass.parse_jass('function main()\nend\n')


@pytest.mark.parametrize('value',('not','true','false','function','null','(','-'))
def test_quoted_keywords_are_literal_strings(value):
    e=program(f'call F("{value}")').functions['Test'].body[0].exprs[0].args[0]
    assert e.kind=='string' and e.value==value


def test_quoted_function_terminator_cannot_end_a_function():
    with pytest.raises(jass.JassParseError):
        jass.parse_jass('function F takes nothing returns nothing\n"endfunction"\n')


def test_elseif_chain_cannot_bypass_nesting_budget(monkeypatch):
    monkeypatch.setattr(jass,'MAX_NESTING',8)
    with pytest.raises(jass.JassParseError,match='上限'):
        program('if true then\n'+('elseif false then\n'*12)+'endif')


def test_program_function_mapping_is_read_only():
    p=program('call F()')
    with pytest.raises(TypeError):p.functions['Other']=p.functions['Test']
