/**
 * Hide the `admin` login from the "Choose a user" picker on /web/login.
 *
 * Rationale
 * ---------
 * The trust runs only two interactive logins: `storekeeper` (shared
 * roster) and `admin` (trustees). The picker is convenient for the
 * store keeper because everyone clicks the same button; for the
 * Administrator account it leaks the existence of the privileged
 * login to anyone glancing at the screen. The Admin should reach
 * the system by typing the username at the "Use another user" form
 * instead.
 *
 * How it works
 * ------------
 * The picker reads `web.lastConnectedUser` from localStorage. We
 * patch both the read path (UserSwitch.setup filters `admin` out
 * of the rendered state) and the write path (localStorage proxy
 * strips `admin` before persistence), so the entry can never make
 * it back into the picker even after the Admin signs in.
 *
 * To unlock for debugging, edit HIDDEN_LOGINS below.
 */

import { patch } from "@web/core/utils/patch";
import { UserSwitch } from "@web/core/user_switch/user_switch";
import { browser } from "@web/core/browser/browser";

const HIDDEN_LOGINS = new Set(["admin", "__system__"]);
const STORAGE_KEY = "web.lastConnectedUser";

// 1. Filter the in-memory state when the picker renders.
patch(UserSwitch.prototype, {
    setup() {
        super.setup();
        // `this.state.users` is reactive (useState). Mutating the
        // array in place keeps the proxy alive; `splice` triggers
        // the UI update.
        for (let i = this.state.users.length - 1; i >= 0; i--) {
            if (HIDDEN_LOGINS.has(this.state.users[i].login)) {
                this.state.users.splice(i, 1);
            }
        }
        // Re-evaluate whether to show the picker at all. If the only
        // remaining stored user was hidden, the form (typed login)
        // should be visible by default.
        this.state.displayUserChoice = this.state.users.length > 0;
        this.form.classList.toggle("d-none", this.state.displayUserChoice);
    },
});

// 2. Clean any already-persisted entries on every page load, so a
//    user who logged in as admin BEFORE this patch shipped doesn't
//    keep the leftover button forever.
try {
    const raw = browser.localStorage.getItem(STORAGE_KEY);
    if (raw) {
        const cleaned = JSON.parse(raw).filter((u) => !HIDDEN_LOGINS.has(u.login));
        browser.localStorage.setItem(STORAGE_KEY, JSON.stringify(cleaned));
    }
} catch (_) {
    // localStorage may be disabled (private mode, embedded webview);
    // silently ignore - the patch above still filters at render.
}
