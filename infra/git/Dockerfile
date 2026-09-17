FROM alpine:3.23

# SSH 只接收公钥；git 用户不允许密码登录，命令入口进一步限定到唯一仓库。
RUN apk add --no-cache git openssh-server openssh-client su-exec \
    && adduser -D -s /bin/sh git && passwd -d git
COPY sshd_config /etc/ssh/sshd_config
COPY entrypoint.sh git-command.sh pre-receive.sh healthcheck.sh /usr/local/bin/
RUN sed -i 's/\r$//' /usr/local/bin/*.sh \
    && chmod 755 /usr/local/bin/*.sh

EXPOSE 22
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=12 \
    CMD ["/usr/local/bin/healthcheck.sh"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
