/** Translate FullClone's formatted readouts without translating map content. */
export function translateFullClone(text: string, label: (value: string) => string): string | undefined {
  let match = /^玩家 (\d+)$/.exec(text)
  if (match) return 'Player ' + match[1]
  match = /^(原生)?队伍 (\d+)(?:（(.+)）)?$/.exec(text)
  if (match) return (match[1] ? 'Native team ' : 'Team ') + match[2] + (match[3] ? ' (' + match[3] + ')' : '')
  match = /^(.+)（队伍 (\d+)）$/.exec(text)
  if (match) return (match[1] === '未读取队伍名' ? label(match[1]) : match[1]) + ' (Team ' + match[2] + ')'
  match = /^(.+)（队伍未确认）$/.exec(text)
  if (match) return match[1] + ' (team unconfirmed)'
  match = /^(.+)（原始队伍值 (.+)）$/.exec(text)
  if (match) return label(match[1]) + ' (raw team: ' + label(match[2]) + ')'
  match = /^特殊中立槽位（原生队伍原始值 (.+)）$/.exec(text)
  if (match) return 'Neutral slot (raw team: ' + match[1] + ')'
  match = /^未分配普通队伍（原始值 (-?\d+)）$/.exec(text)
  if (match) return 'No regular team (raw: ' + match[1] + ')'
  match = /^(.+)（原始值 (-?\d+)）$/.exec(text)
  if (match) return label(match[1]) + ' (raw: ' + match[2] + ')'
  match = /^原始值 (-?\d+)$/.exec(text)
  if (match) return 'Raw value: ' + match[1]
  match = /^(\d+) · ([\u3400-\u9fff]+)$/.exec(text)
  if (match) return match[1] + ' · ' + label(match[2])
  match = /^(Ctrl|Alt)\+空格$/.exec(text)
  if (match) return match[1] + '+Space'
  match = /^地图势力 (\d+)$/.exec(text)
  if (match) return 'Map force ' + match[1]

  match = /^玩家 (\d+)((?:（.*）)?)：((?:原生队伍|未分配普通队伍|特殊中立槽位).+)$/.exec(text)
  if (match) {
    const [, number, suffix, details] = match
    const parts = details.split('；当前外交模板：')
    const name = suffix.replace(/（(中立敌对|中立被动|名称暂无法读取|地图未设置名称)）/g, (_, value: string) => ' (' + label(value) + ')')
    return 'Player ' + number + name + ': ' + label(parts[0]) + (parts[1] ? '; template: ' + label(parts[1]) : '')
  }
  match = /^已恢复玩家 (\d+) 的控制状态$/.exec(text)
  if (match) return "Restored Player " + match[1] + "'s control state."
  match = /^已控制玩家 (\d+)（阵营不变）$/.exec(text)
  if (match) return 'Took control of Player ' + match[1] + '. Alliances are unchanged.'
  match = /^玩家 (\d+) 已套用(.+)外交模板（控制权限保持不变）$/.exec(text)
  if (match) return 'Applied ' + label(match[2]) + ' diplomacy to Player ' + match[1] + '. Shared control is unchanged.'
  match = /^已(恢复|冻结)(\d+)个单位；跳过变化或失效身份(\d+)个$/.exec(text)
  if (match) return (match[1] === '恢复' ? 'Restored ' : 'Froze ') + match[2] + ' units; skipped ' + match[3] + ' changed or stale units.'
  match = /^已按阵型复制(\d+)个单位；技能未完整复制(\d+)项$/.exec(text)
  if (match) return 'Cloned ' + match[1] + ' units in formation. Abilities not fully copied: ' + match[2] + '.'
  match = /^已复制 (\d+) 个单位(?:；有 (\d+) 项技能未完整复制)?$/.exec(text)
  if (match) return 'Cloned ' + match[1] + ' units.' + (match[2] ? ' Abilities not fully copied: ' + match[2] + '.' : '')
  match = /^已聚集 (\d+) 个地面物品(（仅指定物品ID）|（已排除指定ID）)?$/.exec(text)
  if (match) return 'Gathered ' + match[1] + ' ground items.' + (match[2] ? ' ' + label(match[2]) : '')
  match = /^已投放补给物品(\d+)个$/.exec(text)
  if (match) return 'Delivered ' + match[1] + ' supply items.'
  match = /^无法确认玩家 (\d+) 的槽位，未修改外交模板。请重新读取玩家信息$/.exec(text)
  if (match) return "Player "+match[1]+" could not be verified. Refresh the player list."
  match = /^已恢复 (\d+)\/(\d+) 个玩家。玩家 ([\d、]+) 槽位身份未确认，已保留其原记录$/.exec(text)
  if (match) return "Restored "+match[1]+"/"+match[2]+" players. Original records retained for unconfirmed slots "+match[3].replaceAll('、', ', ')+"."
  match = /^已恢复 (\d+) 个玩家真正原队伍（共享控制权限保持不变）$/.exec(text)
  if (match) return 'Restored original alliances for ' + match[1] + ' players. Shared control is unchanged.'
  match = /^已为(.+)补满 (\d+) 个单位的生命魔法（符合范围共 (\d+) 个）$/.exec(text)
  if (match) return 'Refilled ' + match[2] + ' of ' + match[3] + ' eligible units for ' + label(match[1]) + '.'
  match = /^(.+)符合范围的 (\d+) 个单位生命魔法已经全满$/.exec(text)
  if (match) return 'All ' + match[2] + ' eligible units already have full health and mana for ' + label(match[1]) + '.'
  match = /^(.+)没有符合范围的存活、未隐藏单位$/.exec(text)
  if (match) return label(match[1]) + ' has no eligible living, visible units.'
  match = /^已接受鼠标位置(.+)（([!-~]{4})）施法命令，归自己$/.exec(text)
  if (match) return 'Accepted cast at cursor: ' + label(match[1] + ' ' + match[2]) + '. Caster belongs to you.'
  match = /^已转交 (\d+) 个单位；跳过或未确认 (\d+) 个$/.exec(text)
  if (match) return "Transferred "+match[1]+" units. Skipped or unconfirmed: "+match[2]+"."
  match = /^已交换双方共 (\d+) 个英雄技能槽$/.exec(text)
  if (match) return 'Swapped ' + match[1] + ' skill slots across both heroes.'
  match = /^已还原 (\d+) 名英雄；还有 (\d+) 名待还原(?:。(.+))?$/.exec(text)
  if (match) return 'Heroes restored: ' + match[1] + '. Pending: ' + match[2] + '.' + (match[3] ? ' ' + match[3] : '')
  match = /^已确认 (\d+) 个单位归还原玩家；跳过或未确认 (\d+) 个$/.exec(text)
  if (match) return "Restored "+match[1]+" units to their original owners. Skipped or unconfirmed: "+match[2]+"."
  match = /^已处理 (\d+) 个目标$/.exec(text)
  if (match) return 'Processed ' + match[1] + ' targets.'
  match = /^已将 (\d+) 个英雄的等级增加1级$/.exec(text)
  if (match) return 'Added one level to ' + match[1] + ' heroes.'
  match = /^已将 (\d+) 个英雄的力量、敏捷、智力增加2点$/.exec(text)
  if (match) return 'Added 2 strength, agility and intelligence to ' + match[1] + ' heroes.'
  match = /^正在执行 (.+?)(?:\.\.\.|…)$/.exec(text)
  if (match && label(match[1]) !== match[1]) return 'Running ' + label(match[1]) + '…'

  match = /^(地图初始配置未确认|未找到配置文字|本地玩家未确认|实时队伍未确认|发现可能覆盖当前地图的本地文件|无法核对本地文件覆盖)[：:](.+)$/.exec(text)
  if (match) return label(match[1]) + ': ' + label(match[2].trim())
  match = /^玩家(\d+)名字：(.*)$/.exec(text)
  if (match) return 'Player ' + match[1] + ' name: ' + label(match[2])
  match = /^玩家(\d+)的(\w+)本次未读出$/.exec(text)
  if (match) return 'Could not read ' + match[2] + ' for Player ' + match[1] + '.'
  return undefined
}
