# WebNews

Nanna News is an intensive information carrier built with passion by students from various majors at NJU. It strives to collect and organize information at the lowest possible cost and publish it in an easy-to-read format, aiming to break down information barriers and enhance the well-being of fellow students.

WebNews is the web platform for editing and publishing Nanna News.

Our first newsletter was sent on May 23, 2024, using LaTeX. As of March 13, 2025, LaTeX publishing was discontinued, and we transitioned to using Typst for publishing. See [this repo](https://github.com/nik-nul/Nanna_News---LTS) for previous publish workflow and newslettes.

Within NJU, this website began its trial phase within club groups on March 14, 2025. It was adopted for all groups and messages starting March 20, 2025. Finally, on May 20, 2025, we stopped converting messages to LaTeX and moved to an entirely Typst-based workflow.

We are also assisting OUC in establishing its own news service. Their trial period commenced on April 16, 2025, with official publishing starting on April 23, 2025. They began utilizing the Deadline Table feature on May 13, 2025.

If you are interested in creating your own university news group to help more students, please contact me at [231220103@smail.nju.edu.cn](mailto:231220103@smail.nju.edu.cn). I can host a website for you or assist you in deploying this website on your own server.

## Usage and Deployment

1.  **Set up a virtual environment:** Create a virtual environment using your preferred method.
2.  **Install dependencies:** Activate the virtual environment and install the required packages using:
    ```bash
    pip install -r requirements.txt
    ```
    This project was originally developed, tested, and deployed using Python 3.10.12 and latest possible version of those packages. However, it should, in principle, work correctly with most recent Python versions.

3.  **Configuration:**
    * Set the `app.secret_key` in your application configuration.
    * Define your `EDITOR_LIST` and `ADMIN_LIST` to specify user roles.
    * Configure the parameters for `app.run` within the `if __name__ == '__main__':` block to suit your server's web environment.

Once these steps are completed, the application should be ready to run.

**User Registration:**
For security reasons, user registration is restricted by default. If needed, you can temporarily or permanently disable this restriction by commenting out the `@admin_required` decorator above the `register()` function.

Other permission controls are managed similarly.

## Development

This website is currently under active development. Planned features include:

-   [ ] Deployment to GitHub Pages
-   [ ] Email delivery system
-   [ ] (Initiative) RSS feed service

PRs are welcome! To avoid duplicate work, please open a draft PR or an issue to discuss any new features you'd like to contribute before starting development
