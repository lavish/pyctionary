#!/usr/bin/env python3

import sys
import csv
import time
import random
import curses
import signal
import argparse
import subprocess

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
    text_header = u'Pyctionary, a word game for geeks. Press ESC to quit.'
    text_countdown = u'Time left (Ctrl-C to interrupt): '
    text_timeout = u'Time is up!'
    text_dice = u'Roll the dice (1-6): '
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

    def loop(self):
        self.state = 'pick'
        self.next_state = self.state
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
            if key == curses.KEY_RESIZE:
                # clear the screen to avoid artifacts
                self.stdscr.erase()
                # update screen size
                self.check_size()
                self.draw_interface()

            # game automaton
            if self.state == 'pick':
                # game
                self.cell = self.board_str[self.positions[self.active_team]]
                self.next_state = 'watch'
                # interface
                self.blank_card()
                self.card.refresh()
                self.footer.clear()
                self.footer.addstr(1, 1, self.text_pick_card)
            elif self.state == 'watch':
                if key == curses.KEY_ENTER or key == 10 or key == 13:
                    # game
                    self.pick_card()
                    self.next_state = 'draw'
                    # interface (display card)
                    self.update_card()
                    self.footer.clear()
                    if self.all_play:
                        text = self.text_draw_all
                    else:
                        text = self.text_draw
                    self.footer.addstr(1, 1, text)
                    self.card.refresh()
                    self.footer.refresh()
            elif self.state == 'draw':
                if key == curses.KEY_ENTER or key == 10 or key == 13:
                    # game
                    self.time_start = time.time()
                    curses.ungetch(128)
                    Game.interrupted = False
                    self.next_state = 'countdown'
                    # interface (blank card and add countdown text in the footer)
                    self.blank_card()
                    self.card.refresh()
            elif self.state == 'countdown':
                # game
                elapsed = int(time.time() - self.time_start)
                # interface
                if elapsed > self.timeout:
                    self.next_state = 'pre_check'
                    # interface
                    subprocess.Popen(['mplayer', 'data/alarm.mp3'], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
                    self.footer.clear()
                    self.footer.addstr(1, 1, self.text_timeout, curses.A_BOLD)                    
                elif Game.interrupted:
                    self.next_state = 'pre_check'
                    # interface
                    self.footer.clear()
                    curses.ungetch(128)
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
            elif self.state == 'pre_check':
                # game
                self.next_state = 'check'
                # interface
                self.footer.clear()
                if self.all_play:
                    text = u'Winning team '
                    self.footer.addstr(1, 1, text)
                    needle = len(text)
                    text = u', '.join(u'({}){}'.format(team.color[0][0].upper(), team.color[0][1:]) for team in self.teams)
                    text += u', (N)one: '
                    self.footer.addstr(1, 1 + needle, text)
                else:
                    self.footer.addstr(1, 1, self.text_success_or_fail)
                self.update_card()
                self.card.refresh()
                self.footer.refresh()
            elif self.state == 'check':
                # game
                if self.all_play:
                    # all play lasts at most 1 round
                    self.all_play = False
                    team_str = u'bmgy'
                    if key in [ord('N'), ord('n')]:
                        self.active_team = (self.active_team + 1) % len(self.teams)
                        self.next_state = 'pick'
                        # interface
                        self.footer.addch(chr(key))
                    elif key in [ord(x) for x in team_str + team_str.upper()]:
                        for team in self.teams:
                            if team.color[0][0].upper() == chr(key).upper():
                                self.active_team = team.id
                                break
                        self.next_state = 'roll'
                        # interface
                        self.footer.addch(chr(key))
                    else:
                        pass
                    self.footer.refresh()
                else:
                    if key in [ord(x) for x in 'sS']:
                        self.next_state = 'roll'
                        # interface
                        self.footer.addch(chr(key))
                    elif key in [ord('f'), ord('F')]:
                        self.active_team = (self.active_team + 1) % len(self.teams)
                        self.next_state = 'pick'
                        # interface
                        self.footer.addch(chr(key))
                # interface
                self.update_board()
                self.board.refresh()
                self.footer.refresh()
            elif self.state == 'roll':
                self.footer.clear()
                self.footer.addstr(1, 1, self.text_dice)
                self.next_state = 'rolled'
            elif self.state == 'rolled':
                # game
                if key in [ord(str(x)) for x in range(7)]:
                    result = int(chr(key))
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
                    self.next_state = 'pick'
                    # interface
                    self.footer.refresh()
                    self.update_board()
                    self.board.refresh()

            key = self.footer.getch()
            self.state = self.next_state
            time.sleep(0.01)

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
    parser.add_argument('--cards', type=str, default='cards.csv', help='Path to a card file (must be in csv format, default to cards.csv)')
    args = parser.parse_args()

    return args

def die(msg):
    sys.stderr.write(msg)
    sys.stderr.flush()
    sys.exit(1)

def start_game(stdscr, categories, cards, num_teams):
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
        die(u'Minumum term size 104x32, aborting.\n')

if __name__ == '__main__':
    main()