#!/usr/bin/env python3

import sys
import csv
import time
import random
import curses
import signal
import argparse
import subprocess

from enum import Enum
from copy import deepcopy as copy

State = Enum('State', 'pick watch draw countdown check roll')

class ScreenTooSmall(Exception):
    pass

class Team:
    def __init__(self, team_id, color=None):
        self.id = team_id
        self.color = color

class Game:
    board_str = 'ybMgRYbmG*RYbmGyRB*mGyRMbgR*YBmgRbYMg*RyBMgyBmR'
    category_colors = []
    team_colors = []
    interrupted = False

    # all possible game strings
    text_header = u'Pyctionary, a word game for geeks. ESC to quit, \'<\' to undo'
    text_countdown = u'Time left (Ctrl-C to interrupt): '
    text_timeout = u'Time is up!'
    text_dice = u'Roll the dice (1-6 or 0 to randomly advance): '
    text_draw = u'Press ENTER to start drawing'
    text_draw_all = u'ALL PLAY! Press ENTER to start drawing'
    text_success_or_fail = u'(S)uccess or (F)ail? '
    text_pick_card = u'Press ENTER to pick a card'
    text_finish_line = u'Not going forward, finish line already reached'
    fmt_moving = u'Moving forward of {} positions'

    # sand timer, in seconds
    timeout = 60

    def __init__(self, stdscr, categories, cards, num_teams):
        self.stdscr = stdscr
        self.categories = categories
        self.cards = cards
        self.num_teams = num_teams

        self.states = []
        self.state_idx = -1

        self.teams = []
        self.active_team = 0
        self.positions = []
        self.card_data = []
        self.time_start = 0
        self.all_play = False
        self.state = None

        # actual window size
        self.y = curses.LINES-1
        self.x = curses.COLS-1

        # subwindows
        self.header = None
        self.board = None
        self.card = None
        self.legend = None
        self.footer = None

    def team_setup(self):
        for i in range(self.num_teams):
            self.teams.append(Team(i, color=self.team_colors[i]))
            self.positions.append(0)

    def interface_setup(self):
        # hide the cursor
        curses.curs_set(False) 
        # diable newline mode
        curses.nonl()
        # categories
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_BLUE)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_MAGENTA)
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_RED)
        # header and footer
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_CYAN)
        # teams
        curses.init_pair(7, curses.COLOR_BLUE, 0)
        curses.init_pair(8, curses.COLOR_MAGENTA, 0)
        curses.init_pair(9, curses.COLOR_GREEN, 0)
        curses.init_pair(10, curses.COLOR_YELLOW, 0)
        # board: any color
        curses.init_pair(11, curses.COLOR_WHITE, curses.COLOR_WHITE)
        # root background
        curses.init_pair(12, curses.COLOR_BLACK, curses.COLOR_WHITE)

        # define color sets
        self.category_colors = [
            (u'yellow', curses.color_pair(1)),
            (u'blue', curses.color_pair(2)),
            (u'magenta', curses.color_pair(3)),
            (u'green', curses.color_pair(4)),
            (u'red', curses.color_pair(5))]

        self.team_colors = [
            (u'blue', curses.color_pair(7)),
            (u'magenta', curses.color_pair(8)),
            (u'green', curses.color_pair(9)),
            (u'yellow', curses.color_pair(10))]

        # clear screen
        self.stdscr.clear()
        # change root background
        #self.stdscr.bkgd(u' ', curses.color_pair(12) | curses.A_BOLD)

    def draw_header(self):
        self.header = self.stdscr.subwin(1, self.x, 0, 0)
        self.header.bkgd(u' ', curses.color_pair(6) | curses.A_BOLD)
        self.header.addstr(0, 1, self.text_header, curses.color_pair(6))

    def draw_board(self):
        # board
        self.board = self.stdscr.subwin(3 + self.num_teams, self.x, 1, 0)
        self.update_board()

    def update_board(self):
        for i, c in enumerate(self.board_str):
            chars = u'  '
            if c == '*':
                attr = curses.color_pair(11)
            else:
                if c in ['y', 'Y']:
                    attr = curses.color_pair(1)
                elif c in ['b', 'B']:
                    attr = curses.color_pair(2)
                elif c in ['m', 'M']:
                    attr = curses.color_pair(3)
                elif c in ['g', 'G']:
                    attr = curses.color_pair(4)
                else:
                    attr = curses.color_pair(5)
                if c.isupper():
                    chars = u'■■'
            # if (i+1) % 12 == 0:
            #     chars = u'||'
            self.board.addstr(1, 10+2*i, chars, attr | curses.A_BOLD)

        # teams
        for team in self.teams:
            self.board.addstr(3+team.id, 10, (self.positions[team.id] + 1) * u'  ', team.color[1] | curses.A_REVERSE)
            self.board.addstr(3+team.id, 1, u' {}'.format(team.color[0]), team.color[1])
            if self.active_team == team.id:
                self.board.addstr(3+team.id, 1, u'*', team.color[1])

    def draw_card(self):
        tot_y = len(self.categories)*3+2
        tot_x = 40

        self.card = self.stdscr.subwin(tot_y, tot_x, 9+(self.y-tot_y-9-6)//2, (self.x-tot_x)//2)
        self.card.box()

    def update_card(self):
        for i, _ in enumerate(self.categories):
            self.card.addstr(1+i*3, 1, u' '*38, self.category_colors[i][1])
            text = self.card_data[i]
            args = self.category_colors[i][1]
            if self.category_colors[i][0].startswith(self.cell.lower()):
                text = u'*** {} ***'.format(text)
                args = args | curses.A_BOLD
            self.card.addstr(2+i*3, 1, u'{:^38s}'.format(text), args)
            self.card.addstr(3+i*3, 1, u' '*38, self.category_colors[i][1])

    def blank_card(self):
        for i, _ in enumerate(self.categories):
            self.card.addstr(1+i*3, 1, u' '*38)
            self.card.addstr(2+i*3, 1, u' '*38)
            self.card.addstr(3+i*3, 1, u' '*38)

    def draw_legend(self):
        padding = 0
        self.legend = self.stdscr.subwin(3, self.x, self.y-3-3, 0)
        for i, cat in enumerate(self.categories):
            self.legend.addstr(1, 10+padding, u' {} '.format(cat), self.category_colors[i][1])
            padding += len(cat)+3

    def draw_footer(self):
        self.footer = self.stdscr.subwin(3, self.x, self.y-3, 0)
        self.footer.bkgd(u' ', curses.color_pair(6))

    def draw_interface(self):
        self.draw_header()
        self.draw_board()
        self.draw_card()
        self.draw_legend()
        self.draw_footer()
        self.stdscr.refresh()

    def pick_card(self):
        idx = random.choice(range(len(self.cards)))
        self.card_data = self.cards[idx]
        del self.cards[idx]

    def update_countdown(self, elapsed):
        # dark (or red) stripe
        self.footer.addstr(1, 34, u' '*self.timeout,
            curses.color_pair(5) if 10 > (self.timeout - elapsed) else curses.A_REVERSE)
        # white stripe
        self.footer.addstr(1, 34 + (self.timeout - elapsed),
            u' '*elapsed, curses.color_pair(11))

    def check_size(self):
        self.y, self.x = self.stdscr.getmaxyx()
        if self.x < 104 or self.y < 32:
            raise ScreenTooSmall()

    def get_state(self):
        return [
            self.active_team,
            copy(self.positions),
            copy(self.card_data),
            self.all_play,
            self.state,
        ]

    def load_state(self, active_team, positions, card_data, all_play, state):
        self.active_team = active_team
        self.positions = positions
        self.card_data = card_data
        self.all_play = all_play
        self.state = state

    def loop(self):
        self.state = State.pick
        self.state_prev = ''
        self.next_state = self.state
        # randomize acive team on startup
        self.active_team = random.randint(0, len(self.teams))
        key = 0

        self.check_size()
        self.interface_setup()
        self.team_setup()
        self.draw_interface()

        while True: 
            # ESC to quit
            if key == 27:
                break
            # resize window
            elif key == curses.KEY_RESIZE:
                # clear the screen to avoid artifacts
                self.stdscr.erase()
                # update screen size
                self.check_size()
                self.draw_interface()
            elif key == ord('<'):
                if len(self.states) > 0:
                    if self.state in [State.check, State.roll] \
                    or self.state == State.pick and len(self.states) > 1:
                        del self.states[-1]
                    self.load_state(*self.states[-1])
                    self.next_state = self.state
                    self.stdscr.erase()
                    self.draw_interface()
                    self.stdscr.refresh()
            else:
                if self.state_prev != self.state \
                and self.state in [State.pick, State.check, State.roll]:
                    self.states.append(self.get_state())

            # game automaton
            if self.state == State.pick:
                # game
                self.cell = self.board_str[self.positions[self.active_team]]
                if key in [curses.KEY_ENTER, 10, 13]:
                    self.pick_card()
                    self.next_state = State.watch
                    curses.ungetch(128)
                # interface
                self.blank_card()
                self.card.refresh()
                self.footer.clear()
                self.footer.addstr(1, 1, self.text_pick_card)
                self.footer.refresh()

            elif self.state == State.watch:
                # game
                if key in [curses.KEY_ENTER, 10, 13]:
                    self.next_state = State.draw
                    curses.ungetch(128)
                # interface (display card)
                self.update_card()
                self.card.refresh()
                self.footer.clear()
                self.footer.addstr(1, 1, self.text_draw_all if self.all_play else self.text_draw)
                self.footer.refresh()

            elif self.state == State.draw:
                # game
                self.time_start = time.time()
                Game.interrupted = False
                self.next_state = State.countdown
                curses.ungetch(128)
                # interface (blank card and add countdown text in the footer)
                self.blank_card()
                self.card.refresh()

            elif self.state == State.countdown:
                # game
                elapsed = int(time.time() - self.time_start)
                if elapsed > self.timeout:
                    self.next_state = State.check
                    # interface
                    try:
                        subprocess.Popen(['aplay', 'data/alarm.wav'], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
                    except:
                        pass
                    self.footer.clear()
                    self.footer.addstr(1, 1, self.text_timeout)
                    self.footer.refresh()
                    curses.napms(3000)
                    curses.ungetch(128)
                elif Game.interrupted:
                    self.next_state = State.check
                    curses.ungetch(128)
                    # interface
                    self.footer.clear()
                else:
                    try:
                        curses.ungetch(128)
                    except:
                        pass
                    # interface
                    self.footer.addstr(1, 1, self.text_countdown)
                    self.update_countdown(elapsed)
                # interface
                self.footer.refresh()

            elif self.state == State.check:
                # interface
                self.update_card()
                self.card.refresh()
                self.footer.clear()

                # game
                if self.all_play:
                    # interface
                    text = u'Winning team '
                    self.footer.addstr(1, 1, text)
                    needle = len(text)
                    text = u', '.join(u'({}){}'.format(team.color[0][0].upper(), team.color[0][1:]) for team in self.teams)
                    text += u', (N)one: '
                    self.footer.addstr(1, 1 + needle, text)

                    team_str = u'bmgy'
                    if key in [ord('N'), ord('n')]:
                        self.active_team = (self.active_team + 1) % len(self.teams)
                        self.next_state = State.pick
                        # all play lasts at most 1 round
                        self.all_play = False
                        curses.ungetch(128)
                        # interface
                        self.update_board()
                        self.board.refresh()
                        self.footer.addch(chr(key).upper())
                        self.footer.refresh()
                        curses.napms(2000)
                    elif key in [ord(x) for x in team_str + team_str.upper()]:
                        for team in self.teams:
                            if team.color[0][0].upper() == chr(key).upper():
                                self.active_team = team.id
                                break
                        self.next_state = State.roll
                        # all play lasts at most 1 round
                        self.all_play = False
                        curses.ungetch(128)
                        # interface
                        self.footer.addch(chr(key).upper())
                        self.footer.refresh()
                        curses.napms(2000)
                else:
                    # interface
                    self.footer.addstr(1, 1, self.text_success_or_fail)

                    if key in [ord(x) for x in 'sSfF']:
                        upper_key = chr(key).upper()
                        if upper_key == 'S':
                            self.next_state = State.roll
                        else:
                            self.active_team = (self.active_team + 1) % len(self.teams)
                            self.next_state = State.pick    
                        curses.ungetch(128)
                        # interface
                        self.footer.addch(upper_key)
                        self.footer.refresh()
                        curses.napms(2000)

            elif self.state == State.roll:
                # interface
                self.update_board()
                self.board.refresh()
                self.footer.clear()
                self.footer.addstr(1, 1, self.text_dice)

                # game
                if key in [ord(str(x)) for x in range(7)]:
                    if chr(key) == '0':
                        t = time.time()
                        tout = random.randint(2,7)
                        result = 1
                        while (time.time()-t) < tout:
                            result = random.randint(1, 6)
                            self.footer.addch(1, len(self.text_dice) + 1, str(result))
                            self.footer.refresh()
                            curses.napms(100)
                    else:
                        result = int(chr(key))
                        self.footer.addch(1, len(self.text_dice) + 1, str(result))
                    self.footer.refresh()
                    curses.napms(1000)

                    new_position = min(self.positions[self.active_team] + result, len(self.board_str)-1)
                    # interface
                    self.footer.erase()
                    if self.positions[self.active_team] != new_position:
                        if self.board_str[new_position].isupper():
                            self.all_play = True
                        # interface
                        self.footer.addstr(1, 1, self.fmt_moving.format(new_position - self.positions[self.active_team]))
                        # game
                        self.positions[self.active_team] = new_position
                    else:
                        # interface
                        self.footer.addstr(1, 1, self.text_finish_line)
                    # game
                    self.next_state = State.pick
                    # interface
                    self.footer.refresh()
                    self.update_board()
                    self.board.refresh()
                    curses.ungetch(128)
                    curses.napms(2000)


            key = self.footer.getch()
            self.state_prev = self.state
            self.state = self.next_state

            curses.napms(10)

def load_cards(path):
    cards = []
    try:
        with open(path) as f:
            cards = [card for card in csv.reader(f)]
    except:
        die(u'Unable to load the card file, aborting.\n')
    return cards

def signal_handler(signal, frame):
    Game.interrupted = True

def parse_arguments():
    parser = argparse.ArgumentParser(description=u'Pyctionary, a word game for geeks')
    parser.add_argument('--teams', type=int, default=2, help='Number of teams (must be between 2-4, default is 2)')
    parser.add_argument('--cards', type=str, default='cards/it.csv', help='Path to a card file (must be in csv format, default to cards/it.csv)')
    args = parser.parse_args()

    return args

def die(msg):
    sys.stderr.write(msg)
    sys.stderr.flush()
    sys.exit(1)

def start_game(stdscr, categories, cards, num_teams,):
    game = Game(stdscr, categories, cards, num_teams)
    signal.signal(signal.SIGINT, signal_handler)
    game.loop()

def main():
    args = parse_arguments()
    if args.teams > 4 or args.teams < 2:
        die(u'Number of teams must be between 2 and 4.\n')

    cards = load_cards(args.cards)
    categories = cards[0]
    cards = cards[1:]
    try:
        curses.wrapper(start_game, categories, cards, args.teams)
    except ScreenTooSmall:
        die(u'Minimum term size 104x32, aborting.\n')

if __name__ == '__main__':
    main()