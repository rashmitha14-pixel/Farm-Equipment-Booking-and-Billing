"use strict";

// ========================================
// AGRISETU SIMULATED FARMER IVR
// Kannada display + English voice
// ========================================

let token = null;
let stage = "idle";
let lang = "en";
let digits = "";

let farmer = "";
let machines = [];
let selection = null;
let booking = {};

const screen = document.getElementById("screen");
const entry = document.getElementById("entry");
const callStatus = document.getElementById("status");
const audioNotice = document.getElementById("audioNotice");

// ========================================
// LANGUAGE MESSAGES
// [English, Kannada]
// ========================================

const labels = {

    welcome: [
        "Welcome to AgriSetu.\nPress 1 for Kannada.\nPress 2 for English.",
        "ಅಗ್ರಿಸೇತುಗೆ ಸ್ವಾಗತ.\nಕನ್ನಡಕ್ಕಾಗಿ 1 ಒತ್ತಿರಿ.\nಇಂಗ್ಲಿಷ್‌ಗಾಗಿ 2 ಒತ್ತಿರಿ."
    ],

    id: [
        "Enter your numeric Farmer ID. Example: For FE0001, enter 0001. Then press hash.",
        "ನಿಮ್ಮ Farmer ID ಹಾಕಿ.\nಉದಾಹರಣೆ: FE0001 ಇದ್ದರೆ 0001 ಹಾಕಿ.\nನಂತರ # ಒತ್ತಿರಿ."
    ],

    pin: [
        "Enter your four-digit IVR PIN. Then press hash.",
        "ನಿಮ್ಮ ನಾಲ್ಕು ಅಂಕಿಯ IVR PIN ಹಾಕಿ.\nನಂತರ # ಒತ್ತಿರಿ."
    ],

    menu: [
        "MAIN MENU\nPress 1 to book equipment.\nPress 2 to check equipment and rates.\nPress 3 for booking status.\nPress 4 to cancel booking.\nPress 5 for manager assistance.\nPress 0 to end the call.",

        "ಮುಖ್ಯ ಮೆನು\n1 - ಮಷಿನ್ ಬುಕ್ ಮಾಡಲು\n2 - ಮಷಿನ್ ಮತ್ತು ರೇಟ್ ತಿಳಿಯಲು\n3 - ಬುಕ್ಕಿಂಗ್ ಸ್ಟೇಟಸ್\n4 - ಬುಕ್ಕಿಂಗ್ ಕ್ಯಾನ್ಸಲ್ ಮಾಡಲು\n5 - ಮ್ಯಾನೇಜರ್ ಸಹಾಯ\n0 - ಕರೆ ಮುಗಿಸಲು"
    ],

    date: [
        "Enter booking date in year, month, day format. Example: 20261105. Then press hash.",
        "ಬುಕ್ಕಿಂಗ್ ಡೇಟ್ ಹಾಕಿ.\nಮೊದಲು ವರ್ಷ, ನಂತರ ತಿಂಗಳು, ನಂತರ ದಿನ.\nಉದಾಹರಣೆ: 20261105\nನಂತರ # ಒತ್ತಿರಿ."
    ],

    time: [
        "Enter starting time in 24-hour format. Example: 0930 for 9:30 AM. Then press hash.",
        "ಮಷಿನ್ ಬೇಕಾದ ಟೈಮ್ ಹಾಕಿ.\nಉದಾಹರಣೆ: ಬೆಳಿಗ್ಗೆ 9:30ಕ್ಕೆ 0930 ಹಾಕಿ.\nನಂತರ # ಒತ್ತಿರಿ."
    ],

    hours: [
        "Enter how many hours you need the equipment, from 1 to 10. Then press hash.",
        "ಮಷಿನ್ ಎಷ್ಟು ಗಂಟೆ ಬೇಕು ಎಂದು ಹಾಕಿ.\n1 ರಿಂದ 10 ಗಂಟೆ.\nನಂತರ # ಒತ್ತಿರಿ."
    ],

    qty: [
        "Enter how many machines you need. Then press hash.",
        "ಎಷ್ಟು ಮಷಿನ್ ಬೇಕು ಎಂದು ಹಾಕಿ.\nನಂತರ # ಒತ್ತಿರಿ."
    ],

    cancel: [
        "Enter the booking number you want to cancel. Then press hash.",
        "ಕ್ಯಾನ್ಸಲ್ ಮಾಡಬೇಕಾದ ಬುಕ್ಕಿಂಗ್ ನಂಬರ್ ಹಾಕಿ.\nನಂತರ # ಒತ್ತಿರಿ."
    ],

    bye: [
        "Thank you for using AgriSetu. Your call has ended.",
        "ಅಗ್ರಿಸೇತು ಬಳಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು.\nನಿಮ್ಮ ಕರೆ ಮುಗಿದಿದೆ."
    ]

};


// ========================================
// TRANSLATION HELPER
// ========================================

function txt(key) {

    if (!labels[key]) {
        return "";
    }

    return labels[key][lang === "kn" ? 1 : 0];

}


// ========================================
// DISPLAY
// ========================================

function display(message) {

    screen.textContent = message;

    entry.textContent =
        stage === "pin"
            ? "●".repeat(digits.length)
            : digits;

}


// ========================================
// ENGLISH VOICE FOR BOTH LANGUAGES
// ========================================

function voice(message, key = null, englishMessage = null) {

    if (!("speechSynthesis" in window)) {
        return;
    }

    window.speechSynthesis.cancel();

    let spokenText = englishMessage || message;

    // Kannada display, but English voice
    if (lang === "kn" && key && labels[key]) {
        spokenText = labels[key][0];
    }

    const speech = new SpeechSynthesisUtterance(spokenText);

    speech.lang = "en-IN";
    speech.rate = 0.85;
    speech.pitch = 1;
    speech.volume = 1;

    const voices = window.speechSynthesis.getVoices();

    const selectedVoice =
        voices.find(v => v.lang === "en-IN") ||
        voices.find(v => v.lang.toLowerCase().startsWith("en"));

    if (selectedVoice) {
        speech.voice = selectedVoice;
    }

    window.speechSynthesis.speak(speech);

}


// ========================================
// DISPLAY + VOICE
// ========================================

function say(message, key = null, englishMessage = null) {

    display(message);

    voice(message, key, englishMessage);

}


// ========================================
// PROMPT
// ========================================

function prompt(key, nextStage) {

    stage = nextStage;
    digits = "";

    say(txt(key), key);

}


// ========================================
// FLASK API
// ========================================

async function api(path, data = {}) {

    const response = await fetch("/api/ivr/" + path, {

        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({
            ...data,
            token: token
        })

    });

    let result;

    try {
        result = await response.json();
    } catch {
        throw new Error(
            "Server response error. Check your Flask IVR routes."
        );
    }

    if (!response.ok) {
        throw new Error(result.error || "Request failed.");
    }

    return result;

}


// ========================================
// START CALL
// ========================================

async function startCall() {

    if (token) {
        await endCall();
    }

    try {

        const response = await api("start");

        token = response.token;

        lang = "en";
        farmer = "";
        machines = [];
        selection = null;
        booking = {};
        digits = "";

        callStatus.textContent = "● Connected";

        audioNotice.textContent =
            "Kannada option: Kannada display with English voice.";

        prompt("welcome", "language");

    } catch (error) {

        say(error.message);

    }

}


// ========================================
// END CALL
// ========================================

async function endCall() {

    if (token) {

        try {
            await api("end");
        } catch (error) {
            console.error(error);
        }

        token = null;

    }

    stage = "idle";
    digits = "";

    callStatus.textContent = "● Call Ended";

    say(txt("bye"), "bye");

}


// ========================================
// MAIN MENU
// ========================================

function menu() {

    prompt("menu", "menu");

}


// ========================================
// EQUIPMENT LIST
// ========================================

async function equipment(mode) {

    try {

        const response = await api("machines");

        machines = response.machines || [];

        stage = mode;
        digits = "";

        if (machines.length === 0) {

            result(
                "No equipment is currently listed.",
                "No equipment is currently listed."
            );

            return;

        }

        let message = lang === "kn"
            ? "ಮಷಿನ್ ಆಯ್ಕೆ ಮಾಡಿ:\n\n"
            : "Select equipment:\n\n";

        let englishMessage = "Select equipment.\n";

        machines.slice(0, 9).forEach(function (machine, index) {

            const line =
                (index + 1) + ". " +
                machine.name +
                " - Rs. " + machine.rate +
                " per hour - " +
                machine.status +
                " - Stock: " +
                machine.quantity;

            message += line + "\n";

            englishMessage += line + "\n";

        });

        message += lang === "kn"
            ? "\n0 - ಮುಖ್ಯ ಮೆನು"
            : "\n0 - Main menu";

        englishMessage += "\nPress zero for main menu.";

        say(message, null, englishMessage);

    } catch (error) {

        result(error.message);

    }

}


// ========================================
// RESULT SCREEN
// ========================================

function result(message, englishMessage = null) {

    stage = "result";
    digits = "";

    const displayText = message + (
        lang === "kn"
            ? "\n\n0 - ಮುಖ್ಯ ಮೆನು"
            : "\n\n0 - Main menu"
    );

    const spokenText =
        (englishMessage || message) +
        "\nPress zero for main menu.";

    say(displayText, null, spokenText);

}


// ========================================
// SUBMIT DIGITS USING #
// ========================================

async function submit() {

    const value = digits;

    digits = "";
    entry.textContent = "";

    try {

        // FARMER ID

        if (stage === "id") {

            if (!/^\d{1,8}$/.test(value)) {
                throw new Error("Enter a valid numeric Farmer ID.");
            }

            farmer = value;

            prompt("pin", "pin");

            return;

        }


        // IVR PIN AUTHENTICATION

        if (stage === "pin") {

            if (!/^\d{4}$/.test(value)) {
                throw new Error("PIN must contain four digits.");
            }

            const response = await api("auth", {

                farmer_number: farmer,
                pin: value

            });

            farmer = response.code;

            menu();

            return;

        }


        // BOOKING DATE

        if (stage === "date") {

            if (!/^\d{8}$/.test(value)) {
                throw new Error("Enter date as YYYYMMDD.");
            }

            const year = Number(value.slice(0, 4));
            const month = Number(value.slice(4, 6));
            const day = Number(value.slice(6, 8));

            const parsedDate = new Date(Date.UTC(year, month - 1, day));

            if (
                parsedDate.getUTCFullYear() !== year ||
                parsedDate.getUTCMonth() !== month - 1 ||
                parsedDate.getUTCDate() !== day
            ) {
                throw new Error("Invalid booking date.");
            }

            booking.date = value;

            prompt("time", "time");

            return;

        }


        // START TIME

        if (stage === "time") {

            if (!/^([01]\d|2[0-3])[0-5]\d$/.test(value)) {
                throw new Error("Enter a valid time in HHMM format.");
            }

            booking.time = value;

            prompt("hours", "hours");

            return;

        }


        // HOURS

        if (stage === "hours") {

            const hours = Number(value);

            if (
                !/^\d{1,2}$/.test(value) ||
                hours < 1 ||
                hours > 10
            ) {
                throw new Error("Enter hours between 1 and 10.");
            }

            booking.hours = hours;

            prompt("qty", "qty");

            return;

        }


        // QUANTITY + AVAILABILITY CHECK

        if (stage === "qty") {

            const quantity = Number(value);

            if (
                !/^\d+$/.test(value) ||
                quantity < 1
            ) {
                throw new Error("Enter a valid quantity.");
            }

            booking.quantity = quantity;

            const response = await api("check", booking);

            if (!response.available) {

                result(
                    response.error || "Equipment unavailable."
                );

                return;

            }

            stage = "confirm";

            const displayText =
                (lang === "kn"
                    ? "ಮಷಿನ್ ಖಾಲಿ ಇದೆ!\n\n"
                    : "Equipment is available!\n\n") +
                response.machine +
                "\n" +
                response.start +
                " to " +
                response.end +
                "\nQuantity: " +
                response.quantity +
                "\nEstimated bill: Rs. " +
                response.bill +
                "\n\n" +
                (lang === "kn"
                    ? "ಬುಕ್ಕಿಂಗ್ ಓಕೆ ಮಾಡಲು 1 ಒತ್ತಿ.\nಕ್ಯಾನ್ಸಲ್ ಮಾಡಲು 0 ಒತ್ತಿ."
                    : "Press 1 to confirm.\nPress 0 to cancel.");

            const spokenText =
                "Equipment is available. " +
                response.machine +
                ". Quantity " +
                response.quantity +
                ". Estimated bill " +
                response.bill +
                " rupees. Press one to confirm or zero to cancel.";

            say(displayText, null, spokenText);

            return;

        }


        // CANCEL BOOKING

        if (stage === "cancel") {

            if (!/^\d+$/.test(value)) {
                throw new Error("Enter a valid booking number.");
            }

            const response = await api("cancel", {

                booking_id: value

            });

            if (response.ok) {

                result(
                    lang === "kn"
                        ? "ಬುಕ್ಕಿಂಗ್ #" + value + " ಕ್ಯಾನ್ಸಲ್ ಆಗಿದೆ."
                        : "Booking #" + value + " cancelled.",
                    "Booking number " + value + " has been cancelled."
                );

            } else {

                result("Cancellation failed.");

            }

            return;

        }

    } catch (error) {

        // Stay on the same step so the farmer can retry.
        digits = "";

        const message =
            error.message +
            "\nPlease try again and press #.";

        say(message);

    }

}


// ========================================
// VIRTUAL KEYPAD
// ========================================

async function press(key) {

    if (stage === "idle" || stage === "processing") {
        return;
    }


    // LANGUAGE SELECTION

    if (stage === "language") {

        if (key === "1" || key === "2") {

            lang = key === "1" ? "kn" : "en";

            try {

                await api("language", {
                    language: lang
                });

                prompt("id", "id");

            } catch (error) {

                say(error.message);

            }

        }

        return;

    }


    // NUMBER INPUT STAGES

    const inputStages = [
        "id",
        "pin",
        "date",
        "time",
        "hours",
        "qty",
        "cancel"
    ];

    if (inputStages.includes(stage)) {

        if (key === "*") {

            digits = digits.slice(0, -1);

        } else if (key === "#") {

            await submit();
            return;

        } else if (/^\d$/.test(key) && digits.length < 12) {

            digits += key;

        }

        entry.textContent =
            stage === "pin"
                ? "●".repeat(digits.length)
                : digits;

        return;

    }


    // MAIN MENU

    if (stage === "menu") {

        if (key === "0") {

            await endCall();

        } else if (key === "1") {

            await equipment("chooseBooking");

        } else if (key === "2") {

            await equipment("chooseInfo");

        } else if (key === "3") {

            try {

                const response = await api("status");

                const bookings = response.bookings || [];

                if (bookings.length === 0) {

                    result(
                        lang === "kn"
                            ? "ಯಾವುದೇ ಬುಕ್ಕಿಂಗ್ ಇಲ್ಲ."
                            : "No bookings found.",
                        "No bookings found."
                    );

                    return;

                }

                const message = bookings.map(function (b) {

                    return (
                        "#" + b.id +
                        ": " + b.machine_name +
                        "\nStatus: " + b.status +
                        "\nDate: " + b.start_time +
                        "\nBill: Rs. " + b.bill
                    );

                }).join("\n\n");

                result(message);

            } catch (error) {

                result(error.message);

            }

        } else if (key === "4") {

            prompt("cancel", "cancel");

        } else if (key === "5") {

            result(

                lang === "kn"
                    ? "ಸಹಾಯಕ್ಕಾಗಿ ನಿಮ್ಮ ಕೋಆಪರೇಟಿವ್ ಮ್ಯಾನೇಜರ್ ಸಂಪರ್ಕಿಸಿ."
                    : "Please contact your cooperative manager for assistance.",

                "Please contact your cooperative manager for assistance."

            );

        }

        return;

    }


    // SELECT MACHINE

    if (
        stage === "chooseBooking" ||
        stage === "chooseInfo"
    ) {

        if (key === "0") {
            menu();
            return;
        }

        const index = Number(key) - 1;

        if (
            !/^[1-9]$/.test(key) ||
            !machines[index]
        ) {
            return;
        }

        selection = machines[index];

        if (stage === "chooseInfo") {

            const information =
                selection.name +
                "\nRate: Rs. " +
                selection.rate +
                " per hour" +
                "\nStatus: " +
                selection.status +
                "\nTotal stock: " +
                selection.quantity +
                "\nActual availability depends on your selected date and time.";

            result(information);

        } else {

            booking = {
                machine_id: selection.id
            };

            prompt("date", "date");

        }

        return;

    }


    // CONFIRM BOOKING

    if (stage === "confirm") {

        if (key === "0") {

            menu();
            return;

        }

        if (key === "1") {

            stage = "processing";

            say(
                lang === "kn"
                    ? "ನಿಮ್ಮ ಬುಕ್ಕಿಂಗ್ ಪ್ರೊಸೆಸ್ ಆಗುತ್ತಿದೆ..."
                    : "Confirming your booking...",
                null,
                "Confirming your booking. Please wait."
            );

            try {

                const response = await api("book", booking);

                const message =
                    (lang === "kn"
                        ? "ಬುಕ್ಕಿಂಗ್ ಕನ್ಫರ್ಮ್ ಆಗಿದೆ!"
                        : "Booking confirmed!") +
                    "\nBooking number: " +
                    response.booking_id +
                    "\nEstimated bill: Rs. " +
                    response.bill +
                    "\nOwner Dashboard updated.";

                const englishMessage =
                    "Booking confirmed. Your booking number is " +
                    response.booking_id +
                    ". Estimated bill is " +
                    response.bill +
                    " rupees. The owner dashboard has been updated.";

                result(message, englishMessage);

            } catch (error) {

                result(
                    "Booking failed: " + error.message
                );

            }

        }

        return;

    }


    // RETURN FROM RESULT SCREEN

    if (stage === "result" && key === "0") {

        menu();

    }

}


// ========================================
// END CALL WHEN PAGE CLOSES
// ========================================

window.addEventListener("pagehide", function () {

    if (!token) {
        return;
    }

    const payload = JSON.stringify({
        token: token
    });

    navigator.sendBeacon(

        "/api/ivr/end",

        new Blob(
            [payload],
            {
                type: "application/json"
            }
        )

    );

});