# -*- coding: utf-8 -*-

from orgmode import ORGMODE, apply_count, repeat, realign_tags, DIRECTION_FORWARD, DIRECTION_BACKWARD
from orgmode.menu import Submenu, Separator, ActionEntry
from orgmode.keybinding import Keybinding, Plug, MODE_INSERT, MODE_NORMAL
from liborgmode import Heading
from orgmode.exceptions import HeadingDomError

import vim

class EditStructure(object):
	u""" EditStructure plugin """

	def __init__(self):
		u""" Initialize plugin """
		object.__init__(self)
		# menu entries this plugin should create
		self.menu = ORGMODE.orgmenu + Submenu(u'&Edit Structure')

		# key bindings for this plugin
		# key bindings are also registered through the menu so only additional
		# bindings should be put in this variable
		self.keybindings = []

	@classmethod
	def new_heading(cls, below=None, insert_mode=False, end_of_last_child=False):
		u"""
		:below:				True, insert heading below current heading, False,
							insert heading above current heading, None, special
							behavior for insert mode, use the current text as
							heading
		:insert_mode:		True, if action is performed in insert mode
		:end_of_last_child:	True, insert heading at the end of last child,
							otherwise the newly created heading will "take
							over" the current heading's children
		"""
		d = ORGMODE.get_document()
		current_heading = d.current_heading()
		cursor = vim.current.window.cursor[:]
		if not current_heading:
			# the user is in meta data region
			pos = cursor[0] - 1
			heading = Heading(title=d.meta_information[pos], body=d.meta_information[pos + 1:])
			d.headings.insert(0, heading)
			del d.meta_information[pos:]
			d.write()

			if insert_mode:
				vim.command((u'exe "normal %dgg"|startinsert!' % (heading.start_vim, )).encode(u'utf-8'))
			else:
				vim.current.window.cursor = (pos + 1, heading.level + 1)
			return heading

		heading = Heading(level=current_heading.level)

		# it's weird but this is the behavior of original orgmode
		if below is None:
			below = cursor[1] != 0 or end_of_last_child

		heading_insert_position = 0
		if below:
			heading_insert_position = 1
			if not end_of_last_child:
				# append heading at the end of current heading but also take
				# over the children of current heading
				heading.children = current_heading.children[:]
				del current_heading.children

		# insert newly created heading
		l = current_heading.get_parent_list()
		idx = current_heading.get_index_in_parent_list()
		if l is not None and idx is not None:
			l.insert(idx + heading_insert_position, heading)
		else:
			raise HeadingDomError(u'Current heading is not properly linked in DOM')

		d.write()

		# if cursor is currently on a heading, insert parts of it into the
		# newly created heading
		# TODO implement me
		#if insert_mode and not end_of_last_child and cursor[0] == current_heading.start_vim:
		#	if cursor[1] > current_heading.level:
		#		tmp1 = vim.current.buffer[cursor[0] - 1][:cursor[1]].decode(u'utf-8')
		#		tmp2 = vim.current.buffer[cursor[0] - 1][cursor[1]:].decode(u'utf-8')
		#		vim.current.buffer[cursor[0] - 1] = tmp1.encode(u'utf-8')
		#	else:
		#		tmp2 = u''
		#	if below:
		#		vim.current.buffer[cursor[0]:cursor[0]] = [(u'%s %s' % (u'*' * level, tmp2.lstrip())).encode(u'utf-8')]
		#		vim.current.window.cursor = (cursor[0] + 1, level + 1)
		#	else:
		#		# this can only happen at column 0
		#		vim.current.buffer[cursor[0] - 1:cursor[0] - 1] = [(u'%s ' % (u'*' * level, )).encode(u'utf-8')]
		#		vim.current.window.cursor = (cursor[0], level + 1)

		if insert_mode:
			vim.command((u'exe "normal %dgg"|startinsert!' % (heading.start_vim, )).encode(u'utf-8'))
		else:
			vim.current.window.cursor = (cursor[0], cursor[1] + heading.level + 1)

		# return newly created heading
		return heading

	@classmethod
	def _change_heading_level(cls, level, including_children=True, on_heading=False):
		u"""
		Change level of heading realtively with or without including children.
		"""
		d = ORGMODE.get_document()
		current_heading = d.current_heading()
		if not current_heading or on_heading and current_heading.start_vim != vim.current.window.cursor[0]:
			# TODO figure out the actually pressed keybinding and feed these
			# keys instead of making keys up like this
			if level > 0:
				if including_children:
					vim.eval((u'feedkeys(">]]", "n")').encode(u'utf-8'))
				elif on_heading:
					vim.eval(u'feedkeys(">>", "n")'.encode(u'utf-8'))
				else:
					vim.eval(u'feedkeys(">}", "n")'.encode(u'utf-8'))
			else:
				if including_children:
					vim.eval(u'feedkeys("<]]", "n")'.encode(u'utf-8'))
				elif on_heading:
					vim.eval(u'feedkeys("<<", "n")'.encode(u'utf-8'))
				else:
					vim.eval(u'feedkeys("<}", "n")'.encode(u'utf-8'))
			# return True because otherwise apply_count will not work
			return True

		# don't allow demotion below level 1
		if current_heading.level == 1 and level < 1:
			return False

		# reduce level of demotion to a minimum heading level of 1
		if (current_heading.level + level) < 1:
			level = 1

		def indent(heading, ic):
			if not heading:
				return
			heading.level += level

			if ic:
				for child in heading.children:
					indent(child, ic)

		# save cursor position
		c = vim.current.window.cursor[:]

		# indent the promoted/demoted heading
		indent_end_vim = current_heading.end_of_last_child_vim if including_children else current_heading.end_vim
		indent(current_heading, including_children)

		# when changing the level of a heading, it's position in the DOM
		# needs to be updated. It's likely that the heading gets a new
		# parent and new children when demoted or promoted

		# find new parent
		p = current_heading.parent
		pl = current_heading.get_parent_list()
		ps = current_heading.previous_sibling
		nhl = current_heading.level

		def append_heading(heading, parent):
			if heading.level <= parent.level:
				raise ValueError('Heading level not is lower than parent level: %d ! > %d' % (heading.level, parent.level))

			if parent.children and parent.children[-1].level < heading.level:
				append_heading(heading, parent.children[-1])
			else:
				parent.children.append(heading)

		if level > 0:
			# demotion
			# subheading or top level heading
			if ps and nhl > ps.level:
				idx = current_heading.get_index_in_parent_list()
				pl.remove(current_heading)
				# find heading that is the new parent heading
				oh = ps
				h = ps
				while nhl > h.level:
					oh = h
					if h.children:
						h = h.children[-1]
					else:
						break
				np = h if nhl > h.level else oh

				# append current heading to new heading
				np.children.append(current_heading)

				# if children are not included, distribute them among the
				# parent heading and it's siblings
				if not including_children:
					for h in current_heading.children[:]:
						if h.level <= nhl:
							current_heading.children.remove(h)
							append_heading(h, p)
		else:
			# promotion
			if p and nhl <= p.level:
				idx = current_heading.get_index_in_parent_list() + 1
				# find the new parent heading
				oh = p
				h = p
				while nhl <= h.level:
					# append new children to current heading
					[ append_heading(child.copy(), current_heading) for child in h.children[idx:] ]
					del h.children[idx:]
					oh = h
					idx = h.get_index_in_parent_list() + 1
					if h.parent:
						h = h.parent
					else:
						break
				ns = oh.next_sibling
				while ns and ns.level > current_heading.level:
					nns = ns.next_sibling
					append_heading(ns, current_heading)
					ns = nns

				# append current heading to new parent heading / document
				pl.remove(current_heading)
				if nhl > h.level:
					h.children.insert(idx, current_heading)
				else:
					d.headings.insert(idx, current_heading)

		d.write()
		if indent_end_vim != current_heading.start_vim:
			vim.command((u'normal %dggV%dgg=' % (current_heading.start_vim, indent_end_vim)).encode(u'utf-8'))
		# restore cursor position
		vim.current.window.cursor = (c[0], c[1] + level)

		return True

	@classmethod
	@realign_tags
	@repeat
	@apply_count
	def demote_heading(cls, including_children=True, on_heading=False):
		if cls._change_heading_level(1, including_children=including_children, on_heading=on_heading):
			if including_children:
				return u'OrgDemoteSubtree'
			return u'OrgDemoteHeading'

	@classmethod
	@realign_tags
	@repeat
	@apply_count
	def promote_heading(cls, including_children=True, on_heading=False):
		if cls._change_heading_level(-1, including_children=including_children, on_heading=on_heading):
			if including_children:
				return u'OrgPromoteSubtreeNormal'
			return u'OrgPromoteHeadingNormal'

	@classmethod
	def _move_heading(cls, direction=DIRECTION_FORWARD, including_children=True):
		u""" Move heading up or down

		:returns: heading or None
		"""
		d = ORGMODE.get_document()
		heading = d.current_heading()
		if not heading or \
				direction == DIRECTION_FORWARD and not heading.next_sibling or \
				direction == DIRECTION_BACKWARD and not heading.previous_sibling:
			return None

		cursor_offset_within_the_heading_vim = vim.current.window.cursor[0] - (heading._orig_start + 1)

		if not including_children:
			heading.previous_sibling.children.extend(heading.children)
			del heading.children

		heading_insert_position = 1 if direction == DIRECTION_FORWARD else -1
		l = heading.get_parent_list()
		idx = heading.get_index_in_parent_list()
		if l is not None and idx is not None:
			l.insert(idx + heading_insert_position, heading)
		else:
			raise HeadingDomError(u'Current heading is not properly linked in DOM')

		d.write()

		vim.current.window.cursor = (heading.start_vim + cursor_offset_within_the_heading_vim, vim.current.window.cursor[1])

		return True

	@classmethod
	@repeat
	@apply_count
	def move_heading_upward(cls, including_children=True):
		if cls._move_heading(direction=DIRECTION_BACKWARD, including_children=including_children):
			return u'OrgMoveHeadingUpward'

	@classmethod
	@repeat
	@apply_count
	def move_heading_downward(cls, including_children=True):
		if cls._move_heading(direction=DIRECTION_FORWARD, including_children=including_children):
			return u'OrgMoveHeadingDownward'

	def register(self):
		u"""
		Registration of plugin. Key bindings and other initialization should be done.
		"""
		self.keybindings.append(Keybinding(u'<C-S-CR>', Plug(u'OrgNewHeadingAboveNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].new_heading(below=False)<CR>')))
		self.menu + ActionEntry(u'New Heading &above', self.keybindings[-1])
		self.keybindings.append(Keybinding(u'<S-CR>', Plug(u'OrgNewHeadingBelowNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].new_heading(below=True)<CR>')))
		self.menu + ActionEntry(u'New Heading &below', self.keybindings[-1])
		self.keybindings.append(Keybinding(u'<C-CR>', Plug(u'OrgNewHeadingBelowAfterChildrenNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].new_heading(below=True, end_of_last_child=True)<CR>')))
		self.menu + ActionEntry(u'New Heading below, after &children', self.keybindings[-1])

		self.keybindings.append(Keybinding(u'<C-S-CR>', Plug(u'OrgNewHeadingAboveInsert', u'<C-o>:<C-u>silent! py ORGMODE.plugins[u"EditStructure"].new_heading(below=False, insert_mode=True)<CR>', mode=MODE_INSERT)))
		self.keybindings.append(Keybinding(u'<S-CR>', Plug(u'OrgNewHeadingBelowInsert', u'<C-o>:<C-u>silent! py ORGMODE.plugins[u"EditStructure"].new_heading(insert_mode=True)<CR>', mode=MODE_INSERT)))
		self.keybindings.append(Keybinding(u'<C-CR>', Plug(u'OrgNewHeadingBelowAfterChildrenInsert', u'<C-o>:<C-u>silent! py ORGMODE.plugins[u"EditStructure"].new_heading(insert_mode=True, end_of_last_child=True)<CR>', mode=MODE_INSERT)))

		self.menu + Separator()

		self.keybindings.append(Keybinding(u'm{', Plug(u'OrgMoveHeadingUpward', u':silent! py ORGMODE.plugins[u"EditStructure"].move_heading_upward(including_children=False)<CR>')))
		self.keybindings.append(Keybinding(u'm[[', Plug(u'OrgMoveSubtreeUpward', u':silent! py ORGMODE.plugins[u"EditStructure"].move_heading_upward()<CR>')))
		self.menu + ActionEntry(u'Move Subtree &Up', self.keybindings[-1])
		self.keybindings.append(Keybinding(u'm}', Plug(u'OrgMoveHeadingDownward', u':silent! py ORGMODE.plugins[u"EditStructure"].move_heading_downward(including_children=False)<CR>')))
		self.keybindings.append(Keybinding(u'm]]', Plug(u'OrgMoveSubtreeDownward', u':silent! py ORGMODE.plugins[u"EditStructure"].move_heading_downward()<CR>')))
		self.menu + ActionEntry(u'Move Subtree &Down', self.keybindings[-1])

		self.menu + Separator()

		self.menu + ActionEntry(u'&Copy Heading', u'yah', u'yah')
		self.menu + ActionEntry(u'C&ut Heading', u'dah', u'dah')

		self.menu + Separator()

		self.menu + ActionEntry(u'&Copy Subtree', u'yat', u'yat')
		self.menu + ActionEntry(u'C&ut Subtree', u'dat', u'dat')
		self.menu + ActionEntry(u'&Paste Subtree', u'p', u'p')

		self.menu + Separator()

		self.keybindings.append(Keybinding(u'<ah', Plug(u'OrgPromoteHeadingNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].promote_heading(including_children=False)<CR>')))
		self.menu + ActionEntry(u'&Promote Heading', self.keybindings[-1])
		self.keybindings.append(Keybinding(u'<<', Plug(u'OrgPromoteOnHeadingNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].promote_heading(including_children=False, on_heading=True)<CR>')))
		self.keybindings.append(Keybinding(u'<{', u'<Plug>OrgPromoteHeadingNormal', mode=MODE_NORMAL))
		self.keybindings.append(Keybinding(u'<ih', u'<Plug>OrgPromoteHeadingNormal', mode=MODE_NORMAL))

		self.keybindings.append(Keybinding(u'<at', Plug(u'OrgPromoteSubtreeNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].promote_heading()<CR>')))
		self.menu + ActionEntry(u'&Promote Subtree', self.keybindings[-1])
		self.keybindings.append(Keybinding(u'<[[', u'<Plug>OrgPromoteSubtreeNormal', mode=MODE_NORMAL))
		self.keybindings.append(Keybinding(u'<it', u'<Plug>OrgPromoteSubtreeNormal', mode=MODE_NORMAL))

		self.keybindings.append(Keybinding(u'>ah', Plug(u'OrgDemoteHeadingNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].demote_heading(including_children=False)<CR>')))
		self.menu + ActionEntry(u'&Demote Heading', self.keybindings[-1])
		self.keybindings.append(Keybinding(u'>>', Plug(u'OrgDemoteOnHeadingNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].demote_heading(including_children=False, on_heading=True)<CR>')))
		self.keybindings.append(Keybinding(u'>}', u'>Plug>OrgDemoteHeadingNormal', mode=MODE_NORMAL))
		self.keybindings.append(Keybinding(u'>ih', u'>Plug>OrgDemoteHeadingNormal', mode=MODE_NORMAL))

		self.keybindings.append(Keybinding(u'>at', Plug(u'OrgDemoteSubtreeNormal', u':silent! py ORGMODE.plugins[u"EditStructure"].demote_heading()<CR>')))
		self.menu + ActionEntry(u'&Demote Subtree', self.keybindings[-1])
		self.keybindings.append(Keybinding(u'>]]', u'<Plug>OrgDemoteSubtreeNormal', mode=MODE_NORMAL))
		self.keybindings.append(Keybinding(u'>it', u'<Plug>OrgDemoteSubtreeNormal', mode=MODE_NORMAL))

		# other keybindings
		self.keybindings.append(Keybinding(u'<C-d>', Plug(u'OrgPromoteOnHeadingInsert', u'<C-o>:silent! py ORGMODE.plugins[u"EditStructure"].promote_heading(including_children=False, on_heading=True)<CR>', mode=MODE_INSERT)))
		self.keybindings.append(Keybinding(u'<C-t>', Plug(u'OrgDemoteOnHeadingInsert', u'<C-o>:silent! py ORGMODE.plugins[u"EditStructure"].demote_heading(including_children=False, on_heading=True)<CR>', mode=MODE_INSERT)))
